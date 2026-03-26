"""
Unit tests mirroring the async-substrate-interface integration tests:
- test_legacy_decoding
- test_get_events_proper_decoding
- test_old_runtime_calls

These tests exercise the same scalecodec code paths as the integration tests but use
synthetic / fixture data so they run without network access.
"""

import os
import re
import struct
import unittest

from scalecodec.base import RuntimeConfiguration, RuntimeConfigurationObject, ScaleBytes
from scalecodec.type_registry import load_type_registry_file, load_type_registry_preset


def _get_fixture(name: str) -> str:
    module_path = os.path.dirname(__file__)
    fixtures = load_type_registry_file(
        os.path.join(module_path, "fixtures", "metadata_hex.json")
    )
    return fixtures[name]


def _load_kusama_v10_inline() -> str:
    """Return the Kusama V10 metadata hex embedded in test_type_registry.py."""
    registry_path = os.path.join(os.path.dirname(__file__), "test_type_registry.py")
    with open(registry_path) as f:
        content = f.read()
    m = re.search(r'metadata_v10_hex\s*=\s*"(0x[0-9a-f]+)"', content)
    assert m, "Could not find metadata_v10_hex in test_type_registry.py"
    return m.group(1)


class TestLegacyEventDecoding(unittest.TestCase):
    """
    Mirrors test_legacy_decoding: decodes Vec<EventRecord> using legacy (pre-scale-info) metadata.
    The 'attributes' key must exist at the top level of each event dict and contain a list of
    {'type': ..., 'value': ...} parameter dicts.
    """

    # Events payload crafted for Kusama spec_version 1020 (V10 metadata)
    EVENTS_PAYLOAD = (
        "0x14000000000000001027000001010000010000000000102700000001000002000000"
        "000040420f0000010000030000000d05e8f6971c000000000000000000000000000003"
        "000000000101060020a10700000100"
    )

    @classmethod
    def setUpClass(cls):
        RuntimeConfiguration().clear_type_registry()
        RuntimeConfiguration().update_type_registry(load_type_registry_preset("core"))
        RuntimeConfiguration().update_type_registry(load_type_registry_preset("legacy"))
        RuntimeConfiguration().update_type_registry(load_type_registry_preset("kusama"))

        metadata_hex = _load_kusama_v10_inline()
        cls.metadata = RuntimeConfiguration().create_scale_object(
            "MetadataVersioned", ScaleBytes(metadata_hex)
        )
        cls.metadata.decode()
        RuntimeConfiguration().set_active_spec_version_id(1020)

    def test_events_decode_to_list(self):
        events_decoder = RuntimeConfiguration().create_scale_object(
            "Vec<EventRecord>",
            data=ScaleBytes(self.EVENTS_PAYLOAD),
            metadata=self.metadata,
        )
        events_decoder.decode()
        self.assertIsInstance(events_decoder.value, list)
        self.assertGreater(len(events_decoder.value), 0)

    def test_each_event_has_attributes_key(self):
        events_decoder = RuntimeConfiguration().create_scale_object(
            "Vec<EventRecord>",
            data=ScaleBytes(self.EVENTS_PAYLOAD),
            metadata=self.metadata,
        )
        events_decoder.decode()
        for event in events_decoder.value:
            self.assertIn(
                "attributes",
                event,
                f"Event {event.get('event_id')} missing 'attributes' key",
            )

    def test_attributes_is_list_of_param_dicts(self):
        events_decoder = RuntimeConfiguration().create_scale_object(
            "Vec<EventRecord>",
            data=ScaleBytes(self.EVENTS_PAYLOAD),
            metadata=self.metadata,
        )
        events_decoder.decode()
        for event in events_decoder.value:
            attrs = event["attributes"]
            self.assertIsInstance(
                attrs,
                list,
                f"attributes for {event.get('event_id')} should be list, got {type(attrs).__name__}",
            )
            for param in attrs:
                self.assertIn("type", param)
                self.assertIn("value", param)

    def test_event_has_required_keys(self):
        events_decoder = RuntimeConfiguration().create_scale_object(
            "Vec<EventRecord>",
            data=ScaleBytes(self.EVENTS_PAYLOAD),
            metadata=self.metadata,
        )
        events_decoder.decode()
        required_keys = {
            "phase",
            "extrinsic_idx",
            "event_index",
            "module_id",
            "event_id",
            "attributes",
            "topics",
        }
        for event in events_decoder.value:
            self.assertTrue(
                required_keys.issubset(event.keys()),
                f"Event {event.get('event_id')} missing keys: {required_keys - set(event.keys())}",
            )

    def test_last_event_is_extrinsic_failed(self):
        events_decoder = RuntimeConfiguration().create_scale_object(
            "Vec<EventRecord>",
            data=ScaleBytes(self.EVENTS_PAYLOAD),
            metadata=self.metadata,
        )
        events_decoder.decode()
        self.assertEqual(len(events_decoder.value), 5)
        self.assertEqual(events_decoder.value[4]["event_id"], "ExtrinsicFailed")

    def test_event_index_built_from_v10_metadata(self):
        self.assertGreater(len(self.metadata.event_index), 0)
        # event_index keys should be 4-char hex strings
        for key in list(self.metadata.event_index.keys())[:5]:
            self.assertEqual(len(key), 4)
            int(key, 16)  # should parse as hex without error


class TestScaleInfoEventDecoding(unittest.TestCase):
    """
    Mirrors test_get_events_proper_decoding: decodes events using V14 (scale-info) metadata.
    Event 'attributes' must be a tuple of decoded values (not a list of param dicts).
    """

    @classmethod
    def setUpClass(cls):
        RuntimeConfiguration().clear_type_registry()
        RuntimeConfiguration().update_type_registry(load_type_registry_preset("core"))
        RuntimeConfiguration().update_type_registry(load_type_registry_preset("legacy"))
        RuntimeConfiguration().ss58_format = 42  # Bittensor ss58 format

        cls.metadata = RuntimeConfiguration().create_scale_object(
            "MetadataVersioned", ScaleBytes(_get_fixture("bittensor_test"))
        )
        cls.metadata.decode()
        RuntimeConfiguration().add_portable_registry(cls.metadata)

    @classmethod
    def _build_event_bytes(
        cls, phase_bytes: bytes, module_variant: int, inner_variant: int, payload: bytes
    ) -> str:
        """Build a Vec<EventRecord> hex string with one event."""
        vec_len = bytes([0x04])  # Compact(1)
        module = bytes([module_variant])
        inner = bytes([inner_variant])
        topics = bytes([0x00])  # empty topics Vec
        raw = vec_len + phase_bytes + module + inner + payload + topics
        return "0x" + raw.hex()

    def test_no_field_event_attributes_is_none(self):
        """CodeUpdated (variant 2) has no fields → attributes should be None."""
        phase = bytes([0x01])  # Finalization
        # System (variant 0) → CodeUpdated (variant 2)
        hex_data = self._build_event_bytes(
            phase, module_variant=0, inner_variant=2, payload=b""
        )
        decoder = RuntimeConfiguration().create_scale_object(
            "scale_info::19", data=ScaleBytes(hex_data), metadata=self.metadata
        )
        decoder.decode()
        event = decoder.value[0]
        self.assertIsNone(event["attributes"])
        self.assertEqual(event["module_id"], "System")
        self.assertEqual(event["event_id"], "CodeUpdated")

    def test_named_field_event_attributes_is_dict(self):
        """NewAccount (variant 3) has one named field 'account' → attributes should be dict."""
        phase = bytes([0x01])  # Finalization
        account_bytes = bytes(32)  # 32-byte AccountId (all zeros)
        hex_data = self._build_event_bytes(
            phase, module_variant=0, inner_variant=3, payload=account_bytes
        )
        decoder = RuntimeConfiguration().create_scale_object(
            "scale_info::19", data=ScaleBytes(hex_data), metadata=self.metadata
        )
        decoder.decode()
        event = decoder.value[0]
        self.assertIsInstance(event["attributes"], dict)
        self.assertIn("account", event["attributes"])
        self.assertEqual(event["event_id"], "NewAccount")

    def test_unnamed_fields_event_attributes_is_tuple(self):
        """
        NeuronRegistered (SubtensorModule variant 6) has 3 unnamed fields:
        (netuid: u16, uid: u16, AccountId).
        attributes should be a Python tuple.
        """
        phase = bytes([0x01])  # Finalization
        # SubtensorModule is RuntimeEvent variant 7
        netuid = (1).to_bytes(2, "little")
        uid = (100).to_bytes(2, "little")
        account = bytes(32)  # 32-byte AccountId
        payload = netuid + uid + account
        hex_data = self._build_event_bytes(
            phase, module_variant=7, inner_variant=6, payload=payload
        )
        decoder = RuntimeConfiguration().create_scale_object(
            "scale_info::19", data=ScaleBytes(hex_data), metadata=self.metadata
        )
        decoder.decode()
        event = decoder.value[0]
        self.assertIsInstance(event["attributes"], tuple)
        self.assertEqual(len(event["attributes"]), 3)
        netuid_val, uid_val, account_val = event["attributes"]
        self.assertEqual(netuid_val, 1)
        self.assertEqual(uid_val, 100)
        # AccountId should be SS58-encoded when ss58_format is set
        self.assertIsInstance(account_val, str)
        self.assertEqual(
            account_val, "5C4hrfjw9DjXZTzV3MwzrrAr9P1MJhSrvWGWqi1eSuyUpnhM"
        )

    def test_apply_extrinsic_phase(self):
        """Phase::ApplyExtrinsic(u32) sets extrinsic_idx correctly."""
        phase = bytes([0x00]) + (5).to_bytes(4, "little")  # ApplyExtrinsic(5)
        hex_data = self._build_event_bytes(
            phase, module_variant=0, inner_variant=2, payload=b""
        )
        decoder = RuntimeConfiguration().create_scale_object(
            "scale_info::19", data=ScaleBytes(hex_data), metadata=self.metadata
        )
        decoder.decode()
        event = decoder.value[0]
        self.assertEqual(event["phase"], "ApplyExtrinsic")
        self.assertEqual(event["extrinsic_idx"], 5)

    def test_event_has_attributes_key_at_top_level(self):
        """The 'attributes' key must exist at the TOP level of the event dict (not only nested under 'event')."""
        phase = bytes([0x01])  # Finalization
        hex_data = self._build_event_bytes(
            phase, module_variant=0, inner_variant=2, payload=b""
        )
        decoder = RuntimeConfiguration().create_scale_object(
            "scale_info::19", data=ScaleBytes(hex_data), metadata=self.metadata
        )
        decoder.decode()
        event = decoder.value[0]
        self.assertIn("attributes", event)
        # Also nested under 'event'
        self.assertIn("attributes", event["event"])

    def test_event_index_is_built_from_v14_metadata(self):
        """V14 metadata with PortableRegistry should not require event_index (uses scale_info)."""
        # V14 metadata uses the PortableRegistry; event_index on the metadata object
        # itself may be empty (events decoded via scale_info types instead)
        self.assertIsNotNone(self.metadata.portable_registry)


class TestEventIndexBuilding(unittest.TestCase):
    """Tests that metadata correctly builds event_index for legacy (pre-scale-info) versions."""

    @classmethod
    def setUpClass(cls):
        cls.runtime_config = RuntimeConfigurationObject()
        cls.runtime_config.update_type_registry(load_type_registry_preset("core"))
        module_path = os.path.dirname(__file__)
        cls.fixtures = load_type_registry_file(
            os.path.join(module_path, "fixtures", "metadata_hex.json")
        )

    def _decode_metadata(self, version_key: str) -> object:
        metadata = self.runtime_config.create_scale_object(
            "MetadataVersioned", ScaleBytes(self.fixtures[version_key])
        )
        metadata.decode()
        return metadata

    def test_v9_event_index_populated(self):
        metadata = self._decode_metadata("V9")
        self.assertGreater(len(metadata.event_index), 0)

    def test_v10_event_index_populated(self):
        metadata = self._decode_metadata("V10")
        self.assertGreater(len(metadata.event_index), 0)

    def test_v11_event_index_populated(self):
        metadata = self._decode_metadata("V11")
        self.assertGreater(len(metadata.event_index), 0)

    def test_v12_event_index_populated(self):
        metadata = self._decode_metadata("V12")
        self.assertGreater(len(metadata.event_index), 0)

    def test_v13_event_index_populated(self):
        metadata = self._decode_metadata("V13")
        self.assertGreater(len(metadata.event_index), 0)

    def test_event_index_keys_are_4char_hex(self):
        for version in ("V9", "V10", "V11", "V12", "V13"):
            metadata = self._decode_metadata(version)
            for key in metadata.event_index:
                self.assertEqual(len(key), 4, f"{version}: key {key!r} is not 4 chars")
                int(key, 16)  # must be valid hex

    def test_v14_has_portable_registry(self):
        metadata = self._decode_metadata("V14")
        self.assertIsNotNone(metadata.portable_registry)
        self.assertEqual(metadata.value_object[1].index, 14)


class TestRuntimeCallLegacyDecode(unittest.TestCase):
    """
    Mirrors test_old_runtime_calls: tests that Vec<u8> return types are correctly
    identified and decoded through the legacy path.
    """

    @classmethod
    def setUpClass(cls):
        cls.runtime_config = RuntimeConfigurationObject()
        cls.runtime_config.update_type_registry(load_type_registry_preset("core"))
        cls.runtime_config.update_type_registry(load_type_registry_preset("legacy"))

    def test_vec_u8_decodes_as_bytes_type(self):
        """Vec<u8> (Bytes) should decode to a string value."""
        # Encode: Compact(3) + b"abc" = 0x0c616263
        obj = self.runtime_config.create_scale_object(
            "Bytes", data=ScaleBytes("0x0c616263")
        )
        obj.decode()
        self.assertIsNotNone(obj.value)

    def test_compact_u32_decode(self):
        """Basic compact encoding: 1 → 0x04."""
        obj = self.runtime_config.create_scale_object(
            "Compact<u32>", data=ScaleBytes("0x04")
        )
        obj.decode()
        self.assertEqual(obj.value, 1)

    def test_u64_decode(self):
        """u64 LE decode: timestamp value."""
        # 1716358476004 LE = 0xe4b4a18e8f010000
        ts_bytes = (1716358476004).to_bytes(8, "little")
        obj = self.runtime_config.create_scale_object(
            "u64", data=ScaleBytes("0x" + ts_bytes.hex())
        )
        obj.decode()
        self.assertEqual(obj.value, 1716358476004)

    def test_query_map_key_decode_u16(self):
        """u16 key decoding (as used in NetworksAdded query map)."""
        obj = self.runtime_config.create_scale_object("u16", data=ScaleBytes("0x1e00"))
        obj.decode()
        self.assertEqual(obj.value, 30)

    def test_bool_decode_true(self):
        """Bool True decodes from 0x01."""
        obj = self.runtime_config.create_scale_object("bool", data=ScaleBytes("0x01"))
        obj.decode()
        self.assertTrue(obj.value)

    def test_bool_decode_false(self):
        """Bool False decodes from 0x00."""
        obj = self.runtime_config.create_scale_object("bool", data=ScaleBytes("0x00"))
        obj.decode()
        self.assertFalse(obj.value)


if __name__ == "__main__":
    unittest.main()
