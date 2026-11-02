"""Pure-local stress tests: no real wallets, funds or network transfers."""
from __future__ import annotations
import threading
import time
import unittest
from performance_runtime import DesktopExecutor, QueueSaturated
from core.mesh_network import MeshRouter

class FakeRoot:
    def __init__(self):self.calls=[]
    def after(self,ms,callback):self.calls.append((ms,callback));return len(self.calls)
    def after_cancel(self,handle):pass


def spin(predicate,timeout=3.0):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return True
        time.sleep(.004)
    return False

class PerformanceTests(unittest.TestCase):
    def test_callbacks_only_on_main_thread(self):
        ui=threading.get_ident(); thread_ids=[];completed=[]
        p=DesktopExecutor(FakeRoot(),workers=2,queued=3)
        try:
            for i in range(5):
                p.submit(lambda v=i:(thread_ids.append(threading.get_ident()),v)[1],
                         lambda v:completed.append((threading.get_ident(),v)))
            self.assertTrue(spin(lambda:p.stats().completed==5))
            self.assertEqual(completed,[],'Worker called the UI callback')
            self.assertEqual(p.poll(),5)
            self.assertEqual(sorted(x[1] for x in completed),list(range(5)))
            self.assertTrue(all(x[0]==ui for x in completed))
            self.assertTrue(all(t!=ui for t in thread_ids))
        finally:p.close()

    def test_saturated_pool_does_not_block_or_spawn_threads(self):
        hold=threading.Event()
        p=DesktopExecutor(FakeRoot(),workers=2,queued=3)
        try:
            for _ in range(5):p.submit(lambda:hold.wait(5),lambda _:None)
            started=time.monotonic()
            with self.assertRaises(QueueSaturated):p.submit(lambda:1,lambda _:None)
            self.assertLess(time.monotonic()-started,.2)
            self.assertEqual(p.stats().rejected,1)
            self.assertLessEqual(p.stats().peak_active,2)
        finally:
            hold.set()
            self.assertTrue(spin(lambda:p.stats().completed==5))
            p.poll();p.close()

    def test_single_flight_until_delivered(self):
        p=DesktopExecutor(FakeRoot(),workers=1,queued=2)
        try:
            self.assertTrue(p.submit(lambda:3,lambda v:None,key='wallet-balance'))
            self.assertFalse(p.submit(lambda:4,lambda v:None,key='wallet-balance'))
            self.assertTrue(spin(lambda:p.stats().completed==1))
            self.assertFalse(p.submit(lambda:4,lambda v:None,key='wallet-balance'))
            self.assertEqual(p.poll(),1)
            self.assertTrue(p.submit(lambda:5,lambda v:None,key='wallet-balance'))
        finally:p.close()

    def test_failed_task_does_not_reveal_sensitive_details(self):
        messages=[]
        p=DesktopExecutor(FakeRoot(),workers=1,queued=2)
        try:
            def leak():raise RuntimeError('secret seed words and vault password')
            p.submit(leak,None,lambda msg:messages.append(msg))
            self.assertTrue(spin(lambda:p.stats().failed==1))
            p.poll()
            self.assertEqual(messages,['RuntimeError'])
        finally:p.close()

    def test_financial_lane_survives_saturated_rpc_pool(self):
        hold=threading.Event();results=[]
        p=DesktopExecutor(FakeRoot(),workers=2,queued=2)
        try:
            for _ in range(4):p.submit(lambda:hold.wait(5),lambda _:None)
            with self.assertRaises(QueueSaturated):p.submit(lambda:0,lambda _:None)
            p.submit(lambda:'SIGNED TEST ONLY',results.append,lane='financial')
            self.assertTrue(spin(lambda:p.stats().completed>=1))
            p.poll()
            self.assertEqual(results,['SIGNED TEST ONLY'])
        finally:
            hold.set();p.close()

    def test_bounded_poll(self):
        p=DesktopExecutor(FakeRoot(),workers=2,queued=6)
        try:
            values=[]
            for i in range(8):p.submit(lambda v=i:v,values.append)
            self.assertTrue(spin(lambda:p.stats().completed==8))
            self.assertEqual(p.poll(2),2)
            self.assertEqual(len(values),2)
            self.assertEqual(p.poll(6),6)
        finally:p.close()

if __name__=='__main__':unittest.main()
