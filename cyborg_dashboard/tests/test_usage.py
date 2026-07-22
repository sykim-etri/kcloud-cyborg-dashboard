#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import unittest

from cyborg_dashboard.content.admin.accelerator import usage


RP_A = 'rp-aaaa'
RP_B = 'rp-bbbb'
INST_1 = 'inst-1111'
INST_2 = 'inst-2222'


def device(id_=None, uuid=None):
    dev = {}
    if id_ is not None:
        dev['id'] = id_
    if uuid is not None:
        dev['uuid'] = uuid
    return dev


def deployable(device_id, rp_uuid):
    return {'device_id': device_id, 'rp_uuid': rp_uuid}


def arq(rp_uuid, instance_uuid):
    return {'device_rp_uuid': rp_uuid, 'instance_uuid': instance_uuid}


class CorrelateTest(unittest.TestCase):

    def test_binds_instance_through_deployable(self):
        devices = [device(id_=1, uuid='dev-a')]
        result = usage.correlate(
            devices, [deployable(1, RP_A)], [arq(RP_A, INST_1)])
        self.assertEqual([INST_1], result[0]['attached_instances'])
        self.assertEqual(usage.USAGE_IN_USE, result[0]['usage'])

    def test_unbound_device_is_available(self):
        result = usage.correlate([device(id_=1, uuid='dev-a')], [], [])
        self.assertEqual([], result[0]['attached_instances'])
        self.assertEqual(usage.USAGE_AVAILABLE, result[0]['usage'])

    def test_join_falls_back_to_uuid_when_device_has_no_internal_id(self):
        # Cyborg's external representation may expose only ``uuid``; the
        # deployable then references that value as device_id.
        devices = [device(uuid='dev-a')]
        result = usage.correlate(
            devices, [deployable('dev-a', RP_A)], [arq(RP_A, INST_1)])
        self.assertEqual([INST_1], result[0]['attached_instances'])
        self.assertEqual(usage.USAGE_IN_USE, result[0]['usage'])

    def test_usage_unknown_is_not_downgraded_to_available(self):
        # A failed deployable/ARQ lookup must never read as "Available".
        result = usage.correlate(
            [device(id_=1, uuid='dev-a')], [], [], usage_known=False)
        self.assertEqual(usage.USAGE_UNKNOWN, result[0]['usage'])

    def test_same_instance_with_several_arqs_listed_once(self):
        devices = [device(id_=1, uuid='dev-a')]
        result = usage.correlate(
            devices,
            [deployable(1, RP_A), deployable(1, RP_B)],
            [arq(RP_A, INST_1), arq(RP_B, INST_1)])
        self.assertEqual([INST_1], result[0]['attached_instances'])

    def test_distinct_instances_are_both_listed_in_order(self):
        devices = [device(id_=1, uuid='dev-a')]
        result = usage.correlate(
            devices,
            [deployable(1, RP_A), deployable(1, RP_B)],
            [arq(RP_A, INST_1), arq(RP_B, INST_2)])
        self.assertEqual([INST_1, INST_2], result[0]['attached_instances'])

    def test_unbound_arq_without_instance_is_ignored(self):
        devices = [device(id_=1, uuid='dev-a')]
        result = usage.correlate(
            devices, [deployable(1, RP_A)], [arq(RP_A, None)])
        self.assertEqual(usage.USAGE_AVAILABLE, result[0]['usage'])

    def test_arq_for_unknown_rp_is_ignored(self):
        devices = [device(id_=1, uuid='dev-a')]
        result = usage.correlate(
            devices, [deployable(1, RP_A)], [arq('rp-unknown', INST_1)])
        self.assertEqual(usage.USAGE_AVAILABLE, result[0]['usage'])

    def test_deployable_without_rp_uuid_is_skipped(self):
        devices = [device(id_=1, uuid='dev-a')]
        result = usage.correlate(
            devices, [deployable(1, None)], [arq(RP_A, INST_1)])
        self.assertEqual(usage.USAGE_AVAILABLE, result[0]['usage'])

    def test_none_inputs_yield_empty_list(self):
        self.assertEqual([], usage.correlate(None, None, None))

    def test_device_id_zero_is_a_valid_key(self):
        # ``if device_id`` would drop a legitimate id of 0.
        devices = [device(id_=0, uuid='dev-a')]
        result = usage.correlate(
            devices, [deployable(0, RP_A)], [arq(RP_A, INST_1)])
        self.assertEqual([INST_1], result[0]['attached_instances'])

    def test_other_devices_unaffected_by_a_binding(self):
        devices = [device(id_=1, uuid='dev-a'), device(id_=2, uuid='dev-b')]
        result = usage.correlate(
            devices, [deployable(1, RP_A)], [arq(RP_A, INST_1)])
        self.assertEqual(usage.USAGE_IN_USE, result[0]['usage'])
        self.assertEqual(usage.USAGE_AVAILABLE, result[1]['usage'])


class CollectInstanceUuidsTest(unittest.TestCase):

    def test_collects_across_devices(self):
        devices = [{'attached_instances': [INST_1]},
                   {'attached_instances': [INST_1, INST_2]}]
        self.assertEqual({INST_1, INST_2},
                         usage.collect_instance_uuids(devices))

    def test_handles_missing_and_none(self):
        self.assertEqual(set(), usage.collect_instance_uuids(None))
        self.assertEqual(
            set(), usage.collect_instance_uuids([{}, {'attached_instances':
                                                      None}]))


if __name__ == '__main__':
    unittest.main()
