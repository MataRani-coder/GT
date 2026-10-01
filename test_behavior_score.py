from behavior_analyzer import BehaviorAnalyzer, RISK_NONE, RISK_WATCH, RISK_SUSPICIOUS, RISK_HIGH

b = BehaviorAnalyzer(off_hours_start=99, off_hours_end=100)  # disable off-hours for deterministic tests
base = 1_000_000.0

def local_at(seconds):
    return b.score_local('cam_1', 1, base + seconds)

assert local_at(0)['score'] == 0
assert local_at(10)['tier'] in (RISK_NONE, RISK_WATCH)
assert local_at(20)['score'] > 0
# Dwell alone is deliberately insufficient to escalate: the score needs multiple signals.
assert local_at(45)['score'] <= 30
assert not b.should_escalate_to_face('cam_1', 1, base + 45)

# A combination of signals can cross the escalation threshold.
b2 = BehaviorAnalyzer(off_hours_start=99, off_hours_end=100)
b2.update_local('cam_1', 2, base)
rec = b2._local[('cam_1', 2)]
rec.reentry_count = 3
rec.zones_visited = [('cam_1', base), ('cam_2', base + 1), ('cam_3', base + 2)]
d = b2.score_local('cam_1', 2, base + 45)
assert d['score'] >= 60, d
assert d['tier'] in (RISK_SUSPICIOUS, RISK_HIGH)
assert b2.should_escalate_to_face('cam_1', 2, base + 45)
assert '+25' in d['reason']
assert 'Cross-camera movement' in d['reason']
print('behavior risk score tests: PASS')
