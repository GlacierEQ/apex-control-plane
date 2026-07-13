import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from control_plane import ControlPlane, Worker, ANSWER

def test_dispatch():
    cp = ControlPlane()
    cp.register(Worker("w1", 2))
    r = cp.dispatch(1)
    assert r["ok"] and r["worker"]=="w1" and r["answer"]==ANSWER

def test_full():
    cp = ControlPlane()
    cp.register(Worker("w1", 1))
    assert cp.dispatch(1)["ok"]
    assert cp.dispatch(1)["ok"] is False

if __name__=="__main__":
    test_dispatch(); test_full(); print("ok")
