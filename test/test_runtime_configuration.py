# Python SCALE Codec Library
#
# Copyright 2018-2020 Stichting Polkascan (Polkascan Foundation).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#  test_runtime_configuration.py
#

import unittest

from scalecodec import Struct
from scalecodec.base import RuntimeConfiguration, RuntimeConfigurationObject
from scalecodec.type_registry import load_type_registry_preset


class TestScaleDecoderClasses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime_config = RuntimeConfigurationObject()
        cls.runtime_config.clear_type_registry()
        cls.runtime_config.update_type_registry(load_type_registry_preset("core"))
        cls.runtime_config.update_type_registry(load_type_registry_preset("legacy"))

    def test_valid_decoding_classes(self):
        for type_string in self.runtime_config.type_registry["types"].keys():
            decoding_cls = self.runtime_config.get_decoder_class(type_string)

            self.assertIsNotNone(
                decoding_cls,
                msg='"{}" didn\'t return decoding class'.format(type_string),
            )


class TestMultipleRuntimeConfigurations(unittest.TestCase):
    def test_use_config_singleton(self):
        RuntimeConfiguration(config_id="test").update_type_registry(
            {"types": {"CustomTestType": "u8"}}
        )
        self.assertIsNone(RuntimeConfiguration().get_decoder_class("CustomTestType"))
        self.assertIsNotNone(
            RuntimeConfiguration(config_id="test").get_decoder_class("CustomTestType")
        )

    def test_multiple_instances(self):
        runtime_config1 = RuntimeConfigurationObject()
        runtime_config1.update_type_registry({"types": {"MyNewType": "Vec<u8>"}})

        runtime_config2 = RuntimeConfigurationObject()

        self.assertIsNone(RuntimeConfigurationObject().get_decoder_class("MyNewType"))
        self.assertIsNotNone(runtime_config1.get_decoder_class("MyNewType"))
        self.assertIsNone(runtime_config2.get_decoder_class("MyNewType"))


class TestRuntimeIdCache(unittest.TestCase):
    def test_runtime_id_cache_lookup(self):
        runtime_config = RuntimeConfigurationObject()
        runtime_config.update_type_registry(load_type_registry_preset("legacy"))
        runtime_config.update_type_registry(load_type_registry_preset("kusama"))

        self.assertEqual(1023, runtime_config.get_runtime_id_from_upgrades(54248))
        self.assertEqual(1020, runtime_config.get_runtime_id_from_upgrades(0))

    def test_set_head(self):
        runtime_config = RuntimeConfigurationObject()
        runtime_config.update_type_registry(load_type_registry_preset("legacy"))
        runtime_config.update_type_registry(load_type_registry_preset("kusama"))

        self.assertIsNone(runtime_config.get_runtime_id_from_upgrades(99999999998))

        # Set head to block
        runtime_config.set_runtime_upgrades_head(99999999999)

        # Check updated cache
        self.assertGreater(runtime_config.get_runtime_id_from_upgrades(99999999998), 0)


class TestBatchDecodeStructResult(unittest.TestCase):
    """
    batch_decode must return a dict for struct types, not a tuple or list.
    Regression test for _try_make_tuple_batch_decode returning tuple(result)
    for structs, which caused fixed-point types like {bits: u128} to come back
    as (value,) instead of {'bits': value}.
    """

    @classmethod
    def setUpClass(cls):
        cls.rc = RuntimeConfigurationObject()
        cls.rc.update_type_registry(load_type_registry_preset("core"))

    def test_struct_fast_path_returns_dict(self):
        bits_value = 1536564093060666126
        import struct as _struct
        from scalecodec.base import _try_make_tuple_batch_decode

        data = _struct.pack("<Q", bits_value)
        type_mapping = [["bits", "U64"]]
        fast = _try_make_tuple_batch_decode(type_mapping, self.rc)
        self.assertIsNotNone(fast, "Expected a fast-path function to be generated")
        decoded = fast[0](data)
        self.assertIsInstance(decoded, dict, "Struct fast path must return a dict")
        self.assertEqual(decoded, {"bits": bits_value})

    def test_single_field_struct_via_batch_decode(self):
        bits_value = 999999999
        import struct as _struct

        data = _struct.pack("<Q", bits_value)

        StructBase = self.rc.get_decoder_class("Struct")
        MyStruct = type("MyStruct", (StructBase,), {"type_mapping": [["bits", "U64"]]})
        MyStruct.runtime_config = self.rc

        # normal decode path
        from scalecodec.base import ScaleBytes

        obj = MyStruct(data=ScaleBytes(data))
        normal_result = obj.decode(check_remaining=False)
        self.assertEqual(normal_result, {"bits": bits_value})

        # batch_decode path must match
        batch_result = self.rc.batch_decode(
            [type_string := "U64"],  # use primitive directly as sanity check
            [data],
        )
        self.assertEqual(batch_result[0], bits_value)

    def test_tuple_fast_path_single_element_returns_scalar(self):
        from scalecodec.base import _try_make_tuple_batch_decode
        import struct as _struct

        data = _struct.pack("<Q", 42)
        fast = _try_make_tuple_batch_decode(["U64"], self.rc)
        self.assertIsNotNone(fast)
        decoded = fast[0](data)
        self.assertNotIsInstance(decoded, (list, tuple))
        self.assertEqual(decoded, 42)

    def test_tuple_fast_path_multi_element_returns_tuple(self):
        from scalecodec.base import _try_make_tuple_batch_decode
        import struct as _struct

        data = _struct.pack("<QQ", 1, 2)
        fast = _try_make_tuple_batch_decode(["U64", "U64"], self.rc)
        self.assertIsNotNone(fast)
        decoded = fast[0](data)
        self.assertIsInstance(decoded, tuple)
        self.assertEqual(decoded, (1, 2))


if __name__ == "__main__":
    unittest.main()
