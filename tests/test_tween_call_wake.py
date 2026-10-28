"""Exercise the deployed push filter without requiring APNs credentials."""
import ast
import copy
import os
from pathlib import Path
from types import SimpleNamespace
import time
import unittest

SOURCE = Path(os.environ.get('TWEEN_GATEWAY_SOURCE', str(Path(__file__).resolve().parents[1] / 'inventory/host_vars/core.tween.im/files/sygnal/apnspushkin.py')))
tree = ast.parse(SOURCE.read_text())
helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'is_call_wake_notification')
namespace = {'Any': object, 'time': time}
exec(compile(ast.Module(body=[helper], type_ignores=[]), str(SOURCE), 'exec'), namespace)
is_call = namespace['is_call_wake_notification']
# Execute the real payload builder in isolation from APNs/network imports.
klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and any(
    isinstance(m, ast.FunctionDef) and m.name == '_get_payload_full' for m in n.body))
builder = copy.deepcopy(next(m for m in klass.body if isinstance(m, ast.FunctionDef) and m.name == '_get_payload_full'))
for argument in builder.args.args:
    argument.annotation = None
builder.returns = None
namespace['copy'] = copy
exec(compile(ast.Module(body=[builder], type_ignores=[]), str(SOURCE), 'exec'), namespace)
build_payload = namespace['_get_payload_full']


class CallWakeTests(unittest.TestCase):
    def notification(self, **changes):
        content = dict(application='m.call', notify_type='ring', call_id='call-123',
                       expires_at=int(time.time() * 1000) + 90_000)
        content.update(changes)
        return SimpleNamespace(type='org.matrix.msc4075.call.notify', content=content)

    def test_video_ring_payload_preserves_identity_and_contains_no_sdp(self):
        notification = self.notification(call_type='video')
        notification.sender = '@caller:example.org'
        notification.sender_display_name = 'Caller'
        notification.room_id = '!personal:example.org'
        notification.event_id = '$wake'
        notification.room_name = None
        notification.counts = SimpleNamespace(unread=0, missed_calls=0)
        payload = build_payload(SimpleNamespace(MAX_FIELD_LENGTH=1024), notification,
                                SimpleNamespace(data={}), SimpleNamespace(info=lambda *a: None))
        self.assertEqual(payload['type'], notification.type)
        self.assertEqual(payload['content']['call_id'], 'call-123')
        self.assertEqual(payload['content']['application'], 'm.call')
        self.assertEqual(payload['content']['notify_type'], 'ring')
        self.assertEqual(payload['content']['call_type'], 'video')
        self.assertEqual(payload['aps']['alert']['loc-key'], 'VIDEO_CALL_FROM_USER')
        self.assertNotIn('offer', payload['content'])
        self.assertEqual(payload['room_id'], notification.room_id)

    def test_real_invite_still_rings(self):
        self.assertTrue(is_call(SimpleNamespace(type='m.call.invite', content={})))

    def test_encrypted_call_ring_is_forwarded(self):
        self.assertTrue(is_call(self.notification()))

    def test_messages_and_other_signalling_never_become_voip_pushes(self):
        for event_type in ['m.room.encrypted', 'm.room.message', 'm.call.candidates', 'm.call.hangup', None]:
            self.assertFalse(is_call(SimpleNamespace(type=event_type, content={})))

    def test_expired_or_unbounded_notifications_are_dropped(self):
        for expires in [0, '99999999999999', int(time.time() * 1000) - 1000,
                        int(time.time() * 1000) + 300_000]:
            self.assertFalse(is_call(self.notification(expires_at=expires)))

    def test_non_ring_or_missing_identity_does_not_wake_callkit(self):
        for changes in [dict(notify_type='notify'), dict(call_id=''), dict(call_id=None),
                        dict(application='other-app')]:
            self.assertFalse(is_call(self.notification(**changes)))

if __name__ == '__main__':
    unittest.main()
