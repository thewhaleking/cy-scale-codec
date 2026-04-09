#  Polkascan Substrate Interface GUI
#
#  Copyright 2018-2020 openAware BV (NL).
#  This file is part of Polkascan.
#
#  Polkascan is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Polkascan is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Polkascan. If not, see <http://www.gnu.org/licenses/>.
#
#  test_scale_info.py
#
import os
import unittest

from scalecodec.types import GenericAccountId, Null

from scalecodec.base import RuntimeConfigurationObject, ScaleDecoder, ScaleBytes

from scalecodec.type_registry import load_type_registry_file, load_type_registry_preset


class ScaleInfoTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module_path = os.path.dirname(__file__)

        # scale_info_defaults = load_type_registry_file(os.path.join(module_path, 'fixtures', 'scale_info_defaults.json'))

        cls.runtime_config = RuntimeConfigurationObject(ss58_format=42)
        cls.runtime_config.update_type_registry(load_type_registry_preset("core"))
        # cls.runtime_config.update_type_registry(scale_info_defaults)

        cls.metadata_fixture_dict = load_type_registry_file(
            os.path.join(module_path, "fixtures", "metadata_hex.json")
        )

        cls.metadata_obj = cls.runtime_config.create_scale_object(
            "MetadataVersioned", data=ScaleBytes(cls.metadata_fixture_dict["V14"])
        )
        cls.metadata_obj.decode()

        cls.runtime_config.add_portable_registry(cls.metadata_obj)

    def test_path_overrides(self):
        account_cls = self.runtime_config.get_decoder_class("scale_info::0")
        self.assertIsInstance(account_cls(), GenericAccountId)

    def test_primitives(self):
        # scale_info::2 = u8
        obj = self.runtime_config.create_scale_object(
            "scale_info::2", ScaleBytes("0x02")
        )
        obj.decode()
        self.assertEqual(obj.value, 2)

        # scale_info::4 = u32
        obj = self.runtime_config.create_scale_object(
            "scale_info::4", ScaleBytes("0x2efb0000")
        )
        obj.decode()
        self.assertEqual(obj.value, 64302)

    def test_compact(self):
        # scale_info::98 = compact<u32>
        obj = self.runtime_config.create_scale_object(
            "scale_info::98", ScaleBytes("0x02093d00")
        )
        obj.decode()
        self.assertEqual(obj.value, 1000000)

        # scale_info::63 = compact<u128>
        obj = self.runtime_config.create_scale_object(
            "scale_info::63", ScaleBytes("0x130080cd103d71bc22")
        )
        obj.decode()
        self.assertEqual(obj.value, 2503000000000000000)

    def test_array(self):
        # scale_info::14 = [u8; 4]
        obj = self.runtime_config.create_scale_object(
            "scale_info::14",
            ScaleBytes("0x01020304"),
        )
        obj.decode()
        self.assertEqual(obj.value, "0x01020304")

    def test_enum(self):
        # ['sp_runtime', 'generic', 'digest', 'DigestItem']
        obj = self.runtime_config.create_scale_object(
            "sp_runtime::generic::digest::DigestItem", ScaleBytes("0x001054657374")
        )
        obj.decode()
        self.assertEqual({"Other": "Test"}, obj.value)

        obj.encode({"Other": "Test"})
        self.assertEqual(obj.data.to_hex(), "0x001054657374")

    def test_enum_multiple_fields(self):
        obj = self.runtime_config.create_scale_object(
            "sp_runtime::generic::digest::DigestItem",
            ScaleBytes("0x06010203041054657374"),
        )
        obj.decode()

        self.assertEqual({"PreRuntime": ("0x01020304", "Test")}, obj.value)

        data = obj.encode({"PreRuntime": ("0x01020304", "Test")})
        self.assertEqual("0x06010203041054657374", data.to_hex())

    def test_enum_no_value(self):
        obj = self.runtime_config.create_scale_object(
            "scale_info::21", ScaleBytes("0x02")
        )
        obj.decode()
        self.assertEqual("CodeUpdated", obj.value)

    def test_named_struct(self):
        # scale_info::111 = ['frame_support', 'weights', 'RuntimeDbWeight']
        obj = self.runtime_config.create_scale_object(
            "scale_info::111", ScaleBytes("0xe110000000000000d204000000000000")
        )
        obj.decode()

        self.assertEqual(obj.value, {"read": 4321, "write": 1234})

        obj.encode({"read": 4321, "write": 1234})

        self.assertEqual(obj.data.to_hex(), "0xe110000000000000d204000000000000")

    def test_unnamed_struct_one_element(self):
        # ('sp_arithmetic::per_things::percent', <class 'abc.scale_info::205'>)
        obj = self.runtime_config.create_scale_object(
            "scale_info::203", ScaleBytes("0x04")
        )
        obj.decode()
        self.assertEqual(obj.value, 4)

        obj.encode(5)
        self.assertEqual(obj.data.to_hex(), "0x05")

    def test_unnamed_struct_multiple_elements(self):
        # pallet_democracy::vote::PriorLock
        obj = self.runtime_config.create_scale_object(
            "scale_info::377", ScaleBytes("0x0c00000022000000000000000000000000000000")
        )

        obj.decode()
        self.assertEqual((12, 34), obj.value)

        data = obj.encode((12, 34))
        self.assertEqual(data.to_hex(), "0x0c00000022000000000000000000000000000000")

    def test_tuple(self):
        obj = self.runtime_config.create_scale_object(
            "scale_info::73", ScaleBytes("0x0400000003000000")
        )
        obj.decode()

        self.assertEqual((4, 3), obj.value)

    def test_option_none(self):
        obj = self.runtime_config.create_scale_object(
            "scale_info::74", ScaleBytes("0x00")
        )
        obj.decode()

        self.assertIsNone(obj.value)

        data = obj.encode(None)

        self.assertEqual("0x00", data.to_hex())

    def test_option_some(self):
        obj = self.runtime_config.create_scale_object(
            "scale_info::35", ScaleBytes("0x0101")
        )
        obj.decode()
        self.assertEqual("Signed", obj.value)

        data = obj.encode("OnChain")
        self.assertEqual(data.to_hex(), "0x0100")

    def test_weak_bounded_vec(self):
        # 87 = ['frame_support', 'storage', 'weak_bounded_vec', 'WeakBoundedVec']
        obj = self.runtime_config.create_scale_object(
            "scale_info::318",
            ScaleBytes("0x0401020304050607080a00000000000000000000000000000000"),
        )
        obj.decode()

        self.assertEqual(
            [{"id": "0x0102030405060708", "amount": 10, "reasons": "Fee"}], obj.value
        )

        data = obj.encode(
            [{"id": "0x0102030405060708", "amount": 10, "reasons": "Fee"}]
        )
        self.assertEqual(
            "0x0401020304050607080a00000000000000000000000000000000", data.to_hex()
        )

    def test_bounded_vec(self):
        # 'scale_info::90' = frame_support::storage::bounded_vec::BoundedVec
        obj = self.runtime_config.create_scale_object(
            "scale_info::90", ScaleBytes("0x084345")
        )

        obj.decode()

        self.assertEqual("CE", obj.value)

        data = obj.encode([67, 69])
        self.assertEqual("0x084345", data.to_hex())

        data = obj.encode("CE")
        self.assertEqual("0x084345", data.to_hex())

    def test_data(self):
        # 'scale_info::247' = pallet_identity::types::data
        obj = self.runtime_config.create_scale_object(
            "pallet_identity::types::data", ScaleBytes("0x065465737431")
        )
        obj.decode()

        self.assertEqual({"Raw": "Test1"}, obj.value)

        data = obj.encode({"Raw": "Test123"})
        self.assertEqual("0x0854657374313233", data.to_hex())

    def test_era(self):
        # 'scale_info::516' = sp_runtime::generic::era::era
        obj = self.runtime_config.create_scale_object(
            "scale_info::516", ScaleBytes("0x4e9c")
        )
        obj.decode()

        self.assertTupleEqual(obj.value, (32768, 20000))
        self.assertEqual(obj.period, 32768)
        self.assertEqual(obj.phase, 20000)
        self.assertFalse(obj.is_immortal())

    def test_multiaddress(self):
        # 'scale_info::139' = sp_runtime::multiaddress::MultiAddress
        obj = self.runtime_config.create_scale_object(
            "sp_runtime::multiaddress::MultiAddress",
            ScaleBytes(
                "0x00d43593c715fdd31c61141abd04a99fd6822c8558854ccde39a5684e7a56da27d"
            ),
        )

        obj.decode()
        self.assertEqual("5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY", obj.value)
        self.assertEqual(
            "d43593c715fdd31c61141abd04a99fd6822c8558854ccde39a5684e7a56da27d",
            obj.account_id,
        )

        data = obj.encode({"Id": "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"})
        self.assertEqual(
            ScaleBytes(
                "0x00d43593c715fdd31c61141abd04a99fd6822c8558854ccde39a5684e7a56da27d"
            ),
            data,
        )
        self.assertEqual(
            "d43593c715fdd31c61141abd04a99fd6822c8558854ccde39a5684e7a56da27d",
            obj.account_id,
        )

    def test_unknown_scale_info_type(self):
        unknown_type = self.runtime_config.create_scale_object("RegistryType")

        unknown_type.value = {"path": [], "params": [], "def": "unknown", "docs": []}

        with self.assertRaises(NotImplementedError):
            self.runtime_config.get_decoder_class_for_scale_info_definition(
                "unknown::type", unknown_type, "runtime"
            )

    def test_encode_call(self):
        call = self.runtime_config.create_scale_object(
            "Call", metadata=self.metadata_obj
        )
        call.encode(
            {
                "call_module": "Balances",
                "call_function": "transfer",
                "call_args": {
                    "dest": "5GNJqTPyNqANBkUVMN1LPPrxXnFouWXoe2wNSmmEoLctxiZY",
                    "value": 3,
                },
            }
        )
        self.assertEqual(
            call.data.to_hex(),
            "0x060000be5ddb1579b72e84524fc29e78609e3caf42e85aa118ebfe0b0ad404b5bdd25f0c",
        )


class RuntimeSwitchingTestCase(unittest.TestCase):
    """
    Verify that Struct/Enum decoder caches remain correct across runtime switches.

    If the caches are keyed incorrectly (e.g. by id() of an already-freed object),
    a second add_portable_registry call can poison the cache and cause AttributeError
    or wrong values when decoding with a previously-loaded metadata.
    """

    @classmethod
    def setUpClass(cls):
        module_path = os.path.dirname(__file__)
        cls.fixture_dict = load_type_registry_file(
            os.path.join(module_path, "fixtures", "metadata_hex.json")
        )

        cls.rc = RuntimeConfigurationObject(ss58_format=42)
        cls.rc.update_type_registry(load_type_registry_preset("core"))

    def _load_metadata(self, fixture_key):
        meta = self.rc.create_scale_object(
            "MetadataVersioned", data=ScaleBytes(self.fixture_dict[fixture_key])
        )
        meta.decode()
        self.rc.add_portable_registry(meta)
        return meta

    def _decode_u32(self, metadata):
        """Find and decode the u32 type in the current registry, return value."""
        for i in range(20):
            cls = self.rc.get_decoder_class(f"scale_info::{i}")
            if cls is not None and cls.__name__ == "U32":
                obj = self.rc.create_scale_object(
                    f"scale_info::{i}", ScaleBytes("0x01000000"), metadata=metadata
                )
                obj.decode()
                return obj.value
        return None

    def test_runtime_switching_preserves_correctness(self):
        """Switching add_portable_registry must not corrupt the decoder cache."""
        meta_v14 = self._load_metadata("V14")
        result_a1 = self._decode_u32(meta_v14)
        self.assertEqual(result_a1, 1, "First decode with V14 should give 1")

        # Switch to a different runtime
        meta_bittensor = self._load_metadata("bittensor_test")
        result_b = self._decode_u32(meta_bittensor)
        self.assertEqual(result_b, 1, "Decode with bittensor_test should give 1")

        # Switch back to V14 — caches must not carry over stale bittensor entries
        meta_v14_again = self._load_metadata("V14")
        result_a2 = self._decode_u32(meta_v14_again)
        self.assertEqual(
            result_a2,
            1,
            "Second decode with V14 after runtime switch should still give 1",
        )

    def test_two_metadata_objects_decode_independently(self):
        """Two metadata objects from different runtimes must decode independently."""
        meta_v14 = self._load_metadata("V14")
        self.rc.add_portable_registry(meta_v14)

        meta_bittensor = self._load_metadata("bittensor_test")
        self.rc.add_portable_registry(meta_bittensor)

        # Both metadata objects should decode u32 correctly using their own caches
        result_v14 = self._decode_u32(meta_v14)
        result_bittensor = self._decode_u32(meta_bittensor)

        self.assertEqual(result_v14, 1)
        self.assertEqual(result_bittensor, 1)

    def test_instance_type_mapping_not_cached(self):
        """
        Structs that set type_mapping as an instance attribute in __init__ (e.g.
        GenericExtrinsicV4 builds it from signed extensions) must never share a cache
        entry with another instance of the same class that has a different type_mapping.

        This reproduces the bug where the Struct field-decoder cache was keyed only by
        class, causing a second instance with a different type_mapping to use the first
        instance's stale decoders and corrupt the decode stream.
        """
        from scalecodec.types import Struct
        from scalecodec._scale_bytes import ScaleBytes as SB

        rc = RuntimeConfigurationObject()
        rc.update_type_registry(load_type_registry_preset("core"))

        # Two subclasses share the same Python class but build different instance
        # type_mappings in __init__ — simulating GenericExtrinsicV4's pattern.
        class DynamicStruct(Struct):
            def __init__(self, data=None, variant=None, **kwargs):
                # Instance-level type_mapping: variant A = [u8, u16], variant B = [u32]
                if variant == "A":
                    self.type_mapping = [["first", "U8"], ["second", "U16"]]
                else:
                    self.type_mapping = [["value", "U32"]]
                super().__init__(data, **kwargs)

        rc.type_registry["types"]["dynamicstruct"] = DynamicStruct

        # Decode with variant A: 1 byte + 2 bytes = 0x01 0x0200
        obj_a = DynamicStruct(
            data=SB(bytes([0x01, 0x02, 0x00])), variant="A", runtime_config=rc
        )
        obj_a.decode()
        self.assertEqual(obj_a.value["first"], 1)
        self.assertEqual(obj_a.value["second"], 2)

        # Decode with variant B: 4 bytes = 0x05000000
        obj_b = DynamicStruct(
            data=SB(bytes([0x05, 0x00, 0x00, 0x00])), variant="B", runtime_config=rc
        )
        obj_b.decode()
        self.assertEqual(obj_b.value["value"], 5)

        # Decode variant A again — must not use variant B's cached decoders
        obj_a2 = DynamicStruct(
            data=SB(bytes([0x07, 0x08, 0x00])), variant="A", runtime_config=rc
        )
        obj_a2.decode()
        self.assertEqual(obj_a2.value["first"], 7)
        self.assertEqual(obj_a2.value["second"], 8)


if __name__ == "__main__":
    unittest.main()
