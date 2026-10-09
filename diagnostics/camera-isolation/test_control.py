import importlib.util
import json
import stat
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('isolation', Path(__file__).with_name('control.py'))
isolation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolation)


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.gates = self.root/'config'/'blocked'
        self.stack.enter_context(patch.object(isolation, 'ROOT', self.root))
        self.stack.enter_context(patch.object(isolation, 'GATES', self.gates))
        self.stack.enter_context(patch.object(isolation, 'dropin',
            lambda scope, name: self.root/scope/(name+'.d')/isolation.DROPIN))
        self.commands = self.stack.enter_context(patch.object(isolation, 'command'))
        self.properties = self.stack.enter_context(patch.object(isolation, 'properties',
            return_value={'ActiveState':'inactive'}))
        self.stack.enter_context(patch.object(isolation, 'close_desktop_sessions'))
        self.original = {'units': [
            {'scope':'system', 'name':'hailort.service', 'group':'A', 'original':{'ActiveState':'active','SubState':'running'}},
            {'scope':'system', 'name':'lightdm.service', 'group':'B', 'original':{'ActiveState':'active','SubState':'running'}},
            {'scope':'system', 'name':'robotcar@camera.service', 'group':'fixed', 'original':{'ActiveState':'active','SubState':'running'}},
            {'scope':'user', 'name':'pipewire.socket', 'group':'A', 'original':{'ActiveState':'inactive','SubState':'dead'}}
        ], 'groups': {'A':['system:hailort.service','user:pipewire.socket'], 'B':['system:lightdm.service']}}

    def test_baseline_blocks_every_candidate_without_changing_enablement(self):
        isolation.apply(self.original, 'baseline')
        for item in self.original['units']:
            scope, name = item['scope'], item['name']
            self.assertTrue((self.gates/scope/name).exists())
            self.assertIn('ConditionPathExists=!', isolation.dropin(scope,name).read_text())
            self.assertEqual(stat.S_IMODE(isolation.dropin(scope,name).parent.stat().st_mode), 0o755)
        for call in self.commands.call_args_list:
            self.assertNotIn('disable', call.args)
            self.assertNotIn('mask', call.args)
            self.assertNotIn('ssh.service', call.args)
            self.assertNotIn('NetworkManager.service', call.args)

    def test_complementary_groups_keep_normal_capture_fixed_off(self):
        isolation.apply(self.original, 'baseline')
        for group in ('A','B'):
            isolation.apply(self.original, group)
            for item in self.original['units']:
                self.assertEqual((self.gates/item['scope']/item['name']).exists(), item['group'] != group)

    def test_running_candidate_prevents_test_start(self):
        self.properties.return_value = {'ActiveState':'active'}
        with patch.object(isolation.time, 'monotonic', side_effect=[0, 121]):
            with self.assertRaisesRegex(RuntimeError, 'Units did not stop'):
                isolation.apply(self.original, 'baseline')
        self.assertFalse(any('enable' in call.args for call in self.commands.call_args_list))

    def test_custom_split_cannot_enable_fixed_capture_or_unknown_units(self):
        path = self.root/'allowed.json'
        for names in (['system:robotcar@camera.service'], ['system:ssh.service'], ['system:unknown.service']):
            path.write_text(json.dumps(names))
            with self.assertRaises(ValueError):
                isolation.permitted(self.original, 'custom', path)
        path.write_text(json.dumps(['user:pipewire.socket']))
        self.assertEqual(isolation.permitted(self.original,'custom',path), {'user:pipewire.socket'})

    def test_restore_removes_only_own_conditions_and_preserves_inactive_units(self):
        isolation.apply(self.original, 'baseline')
        other = isolation.dropin('system','hailort.service').parent/'existing.conf'
        other.write_text('# pre-existing unrelated setting\n')
        self.commands.reset_mock()
        isolation.restore(self.original)
        self.assertTrue(other.exists())
        for item in self.original['units']:
            self.assertFalse(isolation.dropin(item['scope'],item['name']).exists())
            self.assertFalse((self.gates/item['scope']/item['name']).exists())
        for call in self.commands.call_args_list:
            if 'start' in call.args:
                self.assertNotIn('pipewire.socket', call.args)

    def test_external_dropin_edit_is_preserved(self):
        isolation.apply(self.original, 'baseline')
        path = isolation.dropin('system','hailort.service')
        path.write_text('external change')
        with self.assertRaises(RuntimeError):
            isolation.restore(self.original)
        self.assertEqual(path.read_text(), 'external change')

    def test_runtime_stops_diagnostics_and_only_opens_robot_gates(self):
        isolation.apply(self.original, 'baseline')
        self.commands.reset_mock()
        isolation.runtime(self.original)
        self.commands.assert_any_call('system', 'disable', '--now', *isolation.TESTS)
        self.assertFalse((self.gates/'system'/'robotcar@camera.service').exists())
        self.assertFalse((self.gates/'system'/'hailort.service').exists())
        self.assertTrue((self.gates/'system'/'lightdm.service').exists())
        self.assertTrue((self.gates/'user'/'pipewire.socket').exists())


if __name__ == '__main__':
    unittest.main()
