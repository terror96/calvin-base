# -*- coding: utf-8 -*-

# Copyright (c) 2015 Ericsson AB
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import unittest
import time
import multiprocessing
from calvin.runtime.north import calvin_node
from calvin.Tools import cscompiler as compiler
from calvin.Tools import deployer
import pytest
from calvin.utilities import utils
from calvin.utilities.nodecontrol import dispatch_node
from calvin.utilities.attribute_resolver import format_index_string
from calvin.utilities import calvinlogger
_log = calvinlogger.get_logger(__name__)

def absolute_filename(filename):
    import os.path
    return os.path.join(os.path.dirname(__file__), filename)

rt1 = None
rt2 = None
rt3 = None
kill_peers = True

def setup_module(module):
    global rt1
    global rt2
    global rt3
    global kill_peers
    ip_addr = None

    try:
        ip_addr = os.environ["CALVIN_TEST_IP"]
        purpose = os.environ["CALVIN_TEST_UUID"]
        _log.debug("Running remote tests")
    except KeyError:
        _log.debug("Running lcoal test")
        pass

    if ip_addr:
        remote_node_count = 2
        kill_peers = False
        test_peers = None

        import socket
        ports=[]
        for a in range(2):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('', 0))
            addr = s.getsockname()
            ports.append(addr[1])
            s.close()

        rt1,_ = dispatch_node("calvinip://%s:%s" % (ip_addr, ports[0]), "http://%s:%s" % (ip_addr, ports[1]))

        _log.debug("First runtime started, control http://%s:%s, calvinip://%s:%s" % (ip_addr, ports[1], ip_addr, ports[0]))

        interval = 0.5
        for retries in range(1,20):
            time.sleep(interval)
            _log.debug("Trying to get test nodes for 'purpose' %s" % purpose)
            test_peers = utils.get_index(rt1, format_index_string({'node_name':
                                                                    {'organization': 'com.ericsson',
                                                                     'purpose': purpose}
                                                                  }))
            if not test_peers is None and not test_peers["result"] is None and \
                    len(test_peers["result"]) == remote_node_count:
                test_peers = test_peers["result"]
                break

        if test_peers is None or len(test_peers) != remote_node_count:
            _log.debug("Failed to find all remote nodes within time, peers = %s" % test_peers)
            raise Exception("Not all nodes found dont run tests, peers = %s" % test_peers)

        _log.debug("All remote nodes found!")

        test_peer2_id = test_peers[0]
        test_peer2 = utils.get_node(rt1, test_peer2_id)
        if test_peer2:
            rt2 = utils.RT(test_peer2["control_uri"])
            rt2.id = test_peer2_id
            rt2.uri = test_peer2["uri"]
        test_peer3_id = test_peers[1]
        if test_peer3_id:
            test_peer3 = utils.get_node(rt1, test_peer3_id)
            if test_peer3:
                rt3 = utils.RT(test_peer3["control_uri"])
                rt3.id = test_peer3_id
                rt3.uri = test_peer3["uri"]
    else:
        try:
            ip_addr = os.environ["CALVIN_TEST_LOCALHOST"]
        except:
            import socket
            ip_addr = socket.gethostbyname(socket.gethostname())
        rt1,_ = dispatch_node("calvinip://%s:5000" % (ip_addr,), "http://localhost:5003")
        rt2,_ = dispatch_node("calvinip://%s:5001" % (ip_addr,), "http://localhost:5004")
        rt3,_ = dispatch_node("calvinip://%s:5002" % (ip_addr,), "http://localhost:5005")
        time.sleep(.4)
        utils.peer_setup(rt1, ["calvinip://%s:5001" % (ip_addr,), "calvinip://%s:5002" % (ip_addr, )])
        utils.peer_setup(rt2, ["calvinip://%s:5000" % (ip_addr,), "calvinip://%s:5002" % (ip_addr, )])
        utils.peer_setup(rt3, ["calvinip://%s:5000" % (ip_addr,), "calvinip://%s:5001" % (ip_addr, )])
        time.sleep(.4)


def teardown_module(module):
    global rt1
    global rt2
    global rt3
    global kill_peers

    utils.quit(rt1)
    if kill_peers:
        utils.quit(rt2)
        utils.quit(rt3)
    time.sleep(0.4)
    for p in multiprocessing.active_children():
        p.terminate()
    time.sleep(0.4)

class CalvinTestBase(unittest.TestCase):

    def setUp(self):
        self.rt1 = rt1
        self.rt2 = rt2
        self.rt3 = rt3

    def assert_lists_equal(self, expected, actual, min_length=5):
        self.assertTrue(len(actual) >= min_length, "Received data too short (%d), need at least %d" % (len(actual), min_length))
        l = min([len(expected), len(actual)])
        self.assertListEqual(expected[:l], actual[:l])

@pytest.mark.essential
class TestConnections(CalvinTestBase):

    @pytest.mark.slow
    def testLocalSourceSink(self):
        _log.analyze("TESTRUN", "+", {})
        src = utils.new_actor(self.rt1, 'std.CountTimer', 'src')
        snk = utils.new_actor_wargs(self.rt1, 'io.StandardOut', 'snk', store_tokens=1, quiet=1)

        utils.connect(self.rt1, snk, 'token', self.rt1.id, src, 'integer')

        time.sleep(.5)

        actual = utils.report(self.rt1, snk)

        self.assert_lists_equal(range(1, 10), actual)

        utils.delete_actor(self.rt1, src)
        utils.delete_actor(self.rt1, snk)

    def testMigrateSink(self):
        _log.analyze("TESTRUN", "+", {})
        src = utils.new_actor(self.rt1, 'std.CountTimer', 'src')
        snk = utils.new_actor_wargs(self.rt1, 'io.StandardOut', 'snk', store_tokens=1, quiet=1)

        utils.connect(self.rt1, snk, 'token', self.rt1.id, src, 'integer')

        time.sleep(.4)
        utils.migrate(self.rt1, snk, self.rt2.id)
        time.sleep(.6)

        actual = utils.report(self.rt2, snk)
        self.assert_lists_equal(range(1, 10), actual)

        utils.delete_actor(self.rt1, src)
        utils.delete_actor(self.rt2, snk)

    def testMigrateSource(self):
        _log.analyze("TESTRUN", "+", {})
        src = utils.new_actor(self.rt1, 'std.CountTimer', 'src')
        snk = utils.new_actor_wargs(self.rt1, 'io.StandardOut', 'snk', store_tokens=1, quiet=1)

        utils.connect(self.rt1, snk, 'token', self.rt1.id, src, 'integer')

        time.sleep(1)
        utils.migrate(self.rt1, src, self.rt2.id)

        interval = 0.5
        for retries in range(1,5):
            time.sleep(interval * retries)
            actual = utils.report(self.rt1, snk)
            if len(actual) > 10 :
                break


        self.assert_lists_equal(range(1, 10), actual)

        utils.delete_actor(self.rt2, src)
        utils.delete_actor(self.rt1, snk)

    def testTwoStepMigrateSinkSource(self):
        _log.analyze("TESTRUN", "+", {})
        src = utils.new_actor(self.rt1, 'std.CountTimer', 'src')
        snk = utils.new_actor_wargs(self.rt1, 'io.StandardOut', 'snk', store_tokens=1, quiet=1)

        utils.connect(self.rt1, snk, 'token', self.rt1.id, src, 'integer')

        time.sleep(1)
        utils.migrate(self.rt1, snk, self.rt2.id)
        time.sleep(1)
        utils.migrate(self.rt1, src, self.rt2.id)
        time.sleep(1)

        actual = utils.report(self.rt2, snk)
        self.assert_lists_equal(range(1,15), actual, min_length=10)

        utils.delete_actor(self.rt2, src)
        utils.delete_actor(self.rt2, snk)

    def testTwoStepMigrateSourceSink(self):
        _log.analyze("TESTRUN", "+", {})
        src = utils.new_actor(self.rt1, 'std.CountTimer', 'src')
        snk = utils.new_actor_wargs(self.rt1, 'io.StandardOut', 'snk', store_tokens=1, quiet=1)

        utils.connect(self.rt1, snk, 'token', self.rt1.id, src, 'integer')

        time.sleep(1)
        utils.migrate(self.rt1, src, self.rt2.id)
        utils.report(self.rt1, snk)
        time.sleep(1)
        utils.migrate(self.rt1, snk, self.rt2.id)
        time.sleep(1)

        actual = utils.report(self.rt2, snk)
        self.assert_lists_equal(range(1,20), actual, min_length=15)

        utils.delete_actor(self.rt2, src)
        utils.delete_actor(self.rt2, snk)


@pytest.mark.essential
class TestScripts(CalvinTestBase):

    @pytest.mark.slow
    def testInlineScript(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
          src : std.CountTimer()
          snk : io.StandardOut(store_tokens=1, quiet=1)
          src.integer > snk.token
          """
        app_info, errors, warnings = compiler.compile(script, "simple")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(1)
        snk = d.actor_map['simple:snk']

        actual = utils.report(self.rt1, (snk))
        self.assert_lists_equal(range(1, 20), actual)

        d.destroy()

    @pytest.mark.slow
    def testFileScript(self):
        _log.analyze("TESTRUN", "+", {})
        scriptname = 'test1'
        scriptfile = absolute_filename("scripts/%s.calvin" % (scriptname, ))
        app_info, errors, warnings = compiler.compile_file(scriptfile)
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(1)
        src = d.actor_map['%s:src' % scriptname]
        snk = d.actor_map['%s:snk' % scriptname]

        actual = utils.report(self.rt1, snk)
        self.assert_lists_equal(range(1, 20), actual)

        d.destroy()


class TestStateMigration(CalvinTestBase):

    def testSimpleState(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
          src : std.CountTimer()
          sum : std.Sum()
          snk : io.StandardOut(store_tokens=1, quiet=1)
          src.integer > sum.integer
          sum.integer > snk.token
          """
        app_info, errors, warnings = compiler.compile(script, "simple")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(1)
        csum = d.actor_map['simple:sum']
        snk = d.actor_map['simple:snk']

        utils.migrate(self.rt1, csum, self.rt2.id)
        time.sleep(1)

        actual = utils.report(self.rt1, snk)
        expected = [sum(range(i+1)) for i in range(1,10)]

        self.assert_lists_equal(expected, actual)

        d.destroy()


@pytest.mark.slow
@pytest.mark.essential
class TestAppLifeCycle(CalvinTestBase):

    def testAppDestructionOneRemote(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
          src : std.CountTimer()
          sum : std.Sum()
          snk : io.StandardOut(store_tokens=1, quiet=1)
          src.integer > sum.integer
          sum.integer > snk.token
          """
        app_info, errors, warnings = compiler.compile(script, "simple")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(1)
        src = d.actor_map['simple:src']
        csum = d.actor_map['simple:sum']
        snk = d.actor_map['simple:snk']

        utils.migrate(self.rt1, csum, self.rt2.id)
        time.sleep(.5)

        actual = utils.report(self.rt1, snk)
        expected = [sum(range(i+1)) for i in range(1,10)]
        self.assert_lists_equal(expected, actual)
        utils.delete_application(self.rt1, d.app_id)

        for a in range(0, 20):
            all_removed = None
            try:
                self.assertIsNone(utils.get_actor(self.rt1, src))
                self.assertIsNone(utils.get_actor(self.rt1, csum))
                self.assertIsNone(utils.get_actor(self.rt1, snk))
                self.assertIsNone(utils.get_actor(self.rt2, src))
                self.assertIsNone(utils.get_actor(self.rt2, csum))
                self.assertIsNone(utils.get_actor(self.rt2, snk))
                self.assertIsNone(utils.get_actor(self.rt3, src))
                self.assertIsNone(utils.get_actor(self.rt3, csum))
                self.assertIsNone(utils.get_actor(self.rt3, snk))
            except AssertionError as e:
                print a, e
                all_removed = e
            if all_removed is None:
                break
            time.sleep(1)

        if all_removed:
            raise all_removed

        self.assertIsNone(utils.get_application(self.rt1, d.app_id))
        self.assertIsNone(utils.get_application(self.rt2, d.app_id))
        self.assertIsNone(utils.get_application(self.rt3, d.app_id))

    def testAppDestructionAllRemote(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
          src : std.CountTimer()
          sum : std.Sum()
          snk : io.StandardOut(store_tokens=1, quiet=1)
          src.integer > sum.integer
          sum.integer > snk.token
          """
        import sys
        from twisted.python import log
        log.startLogging(sys.stdout)

        app_info, errors, warnings = compiler.compile(script, "simple")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.2)
        src = d.actor_map['simple:src']
        csum = d.actor_map['simple:sum']
        snk = d.actor_map['simple:snk']

        utils.migrate(self.rt1, src, self.rt2.id)
        utils.migrate(self.rt1, csum, self.rt2.id)
        utils.migrate(self.rt1, snk, self.rt2.id)
        time.sleep(.5)

        actual = utils.report(self.rt2, snk)
        expected = [sum(range(i+1)) for i in range(1,10)]
        self.assert_lists_equal(expected, actual)
        utils.delete_application(self.rt1, d.app_id)

        for a in range(20):
            all_removed = None
            try:
                self.assertIsNone(utils.get_actor(self.rt1, csum))
                self.assertIsNone(utils.get_actor(self.rt1, snk))
                self.assertIsNone(utils.get_actor(self.rt2, src))
                self.assertIsNone(utils.get_actor(self.rt2, csum))
                self.assertIsNone(utils.get_actor(self.rt2, snk))
                self.assertIsNone(utils.get_actor(self.rt3, src))
                self.assertIsNone(utils.get_actor(self.rt3, csum))
                self.assertIsNone(utils.get_actor(self.rt3, snk))
            except AssertionError as e:
                print a, e
                all_removed = e
            if all_removed is None:
                break
            time.sleep(1)

        if all_removed:
            raise all_removed

        self.assertIsNone(utils.get_application(self.rt1, d.app_id))
        self.assertIsNone(utils.get_application(self.rt2, d.app_id))
        self.assertIsNone(utils.get_application(self.rt3, d.app_id))


@pytest.mark.essential
class TestEnabledToEnabledBug(CalvinTestBase):

    def test10(self):
        _log.analyze("TESTRUN", "+", {})
        # Two actors, doesn't seem to trigger the bug
        src = utils.new_actor(self.rt1, 'std.Counter', 'src')
        snk = utils.new_actor_wargs(self.rt1, 'io.StandardOut', 'snk', store_tokens=1, quiet=1)

        utils.connect(self.rt1, snk, 'token', self.rt1.id, src, 'integer')

        time.sleep(0.1)

        actual = utils.report(self.rt1, snk)

        self.assert_lists_equal(range(1, 10), actual)

        utils.delete_actor(self.rt1, src)
        utils.delete_actor(self.rt1, snk)

    def test11(self):
        _log.analyze("TESTRUN", "+", {})
        # Same as test10, but scripted
        script = """
            src : std.Counter()
            snk : io.StandardOut(store_tokens=1, quiet=1)

            src.integer > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "simple")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()

        time.sleep(0.06)

        snk = d.actor_map['simple:snk']
        actual = utils.report(self.rt1, snk)

        self.assert_lists_equal(range(1, 10), actual)

        d.destroy()

    def test20(self):
        _log.analyze("TESTRUN", "+", {})
        src = utils.new_actor(self.rt1, 'std.Counter', 'src')
        ity = utils.new_actor(self.rt1, 'std.Identity', 'ity')
        snk = utils.new_actor_wargs(self.rt1, 'io.StandardOut', 'snk', store_tokens=1, quiet=1)

        utils.connect(self.rt1, snk, 'token', self.rt1.id, ity, 'token')
        utils.connect(self.rt1, ity, 'token', self.rt1.id, src, 'integer')

        time.sleep(0.2)

        actual = utils.report(self.rt1, snk)

        self.assert_lists_equal(range(1, 11), actual)

        utils.delete_actor(self.rt1, src)
        utils.delete_actor(self.rt1, ity)
        utils.delete_actor(self.rt1, snk)

    def test21(self):
        _log.analyze("TESTRUN", "+", {})
        src = utils.new_actor(self.rt1, 'std.Counter', 'src')
        ity = utils.new_actor(self.rt2, 'std.Identity', 'ity')
        snk = utils.new_actor_wargs(self.rt3, 'io.StandardOut', 'snk', store_tokens=1, quiet=1)

        utils.connect(self.rt3, snk, 'token', self.rt2.id, ity, 'token')
        utils.connect(self.rt2, ity, 'token', self.rt1.id, src, 'integer')

        interval = 0.5

        for retries in range(1, 5):
            time.sleep(retries * interval)
            actual = utils.report(self.rt3, snk)
            if len(actual) > 10:
                break

        while len(actual) < 10:
            time.sleep(0.1)
            actual = utils.report(self.rt3, snk)

        self.assert_lists_equal(range(1, 11), actual)

        utils.delete_actor(self.rt1, src)
        utils.delete_actor(self.rt2, ity)
        utils.delete_actor(self.rt3, snk)

    def test22(self):
        _log.analyze("TESTRUN", "+", {})
        src = utils.new_actor(self.rt1, 'std.Counter', 'src')
        ity = utils.new_actor(self.rt2, 'std.Identity', 'ity')
        snk = utils.new_actor_wargs(self.rt3, 'io.StandardOut', 'snk', store_tokens=1, quiet=1)

        utils.connect(self.rt2, ity, 'token', self.rt1.id, src, 'integer')
        utils.connect(self.rt3, snk, 'token', self.rt2.id, ity, 'token')

        interval = 0.5

        for retries in range(1, 5):
            time.sleep(retries * interval)
            actual = utils.report(self.rt3, snk)
            if len(actual) > 10:
                break

        self.assert_lists_equal(range(1, 11), actual)

        time.sleep(0.1)

        actual = utils.report(self.rt3, snk)

        self.assert_lists_equal(range(1, 10), actual)

        utils.delete_actor(self.rt1, src)
        utils.delete_actor(self.rt2, ity)
        utils.delete_actor(self.rt3, snk)

    def test25(self):
        _log.analyze("TESTRUN", "+", {})
        src = utils.new_actor(self.rt1, 'std.Counter', 'src')
        ity = utils.new_actor(self.rt1, 'std.Identity', 'ity')
        snk = utils.new_actor_wargs(self.rt1, 'io.StandardOut', 'snk', store_tokens=1, quiet=1)

        utils.connect(self.rt1, ity, 'token', self.rt1.id, src, 'integer')
        utils.connect(self.rt1, snk, 'token', self.rt1.id, ity, 'token')

        time.sleep(0.2)

        actual = utils.report(self.rt1, snk)

        self.assert_lists_equal(range(1, 10), actual)

        utils.delete_actor(self.rt1, src)
        utils.delete_actor(self.rt1, ity)
        utils.delete_actor(self.rt1, snk)

    def test26(self):
        _log.analyze("TESTRUN", "+", {})
        # Same as test20
        script = """
            src : std.Counter()
            ity : std.Identity()
            snk : io.StandardOut(store_tokens=1, quiet=1)

            src.integer > ity.token
            ity.token > snk.token
          """
        app_info, errors, warnings = compiler.compile(script, "simple")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.4)

        snk = d.actor_map['simple:snk']
        actual = utils.report(self.rt1, snk)
        expected = list(range(1, 10))

        self.assert_lists_equal(expected, actual)

        d.destroy()

    def test30(self):
        _log.analyze("TESTRUN", "+", {})
        src = utils.new_actor(self.rt1, 'std.Counter', 'src')
        snk1 = utils.new_actor_wargs(self.rt1, 'io.StandardOut', 'snk1', store_tokens=1, quiet=1)
        snk2 = utils.new_actor_wargs(self.rt1, 'io.StandardOut', 'snk2', store_tokens=1, quiet=1)

        utils.set_port_property(self.rt1, src, 'out', 'integer', 'fanout', 2)

        utils.connect(self.rt1, snk1, 'token', self.rt1.id, src, 'integer')
        utils.connect(self.rt1, snk2, 'token', self.rt1.id, src, 'integer')

        time.sleep(0.2)

        actual1 = utils.report(self.rt1, snk1)
        actual2 = utils.report(self.rt1, snk2)

        self.assert_lists_equal(list(range(1, 10)), actual1)
        self.assert_lists_equal(list(range(1, 10)), actual2)

        utils.delete_actor(self.rt1, src)
        utils.delete_actor(self.rt1, snk1)
        utils.delete_actor(self.rt1, snk2)

    def test31(self):
        # Verify that fanout defined implicitly in scripts is handled correctly
        _log.analyze("TESTRUN", "+", {})
        script = """
            src : std.Counter()
            snk1 : io.StandardOut(store_tokens=1, quiet=1)
            snk2 : io.StandardOut(store_tokens=1, quiet=1)

            src.integer > snk1.token
            src.integer > snk2.token
        """
        app_info, errors, warnings = compiler.compile(script, "test31")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.1)

        snk1 = d.actor_map['test31:snk1']
        snk2 = d.actor_map['test31:snk2']
        actual1 = utils.report(self.rt1, snk1)
        actual2 = utils.report(self.rt1, snk2)
        expected = list(range(1, 10))

        self.assert_lists_equal(expected, actual1)
        self.assert_lists_equal(expected, actual2)

        d.destroy()

    def test32(self):
        # Verify that fanout from component inports is handled correctly
        _log.analyze("TESTRUN", "+", {})
        script = """
            component Foo() in -> a, b{
              a : std.Identity()
              b : std.Identity()
              .in >  a.token
              .in > b.token
              a.token > .a
              b.token > .b
            }

            snk2 : io.StandardOut(store_tokens=1, quiet=1)
            snk1 : io.StandardOut(store_tokens=1, quiet=1)
            foo : Foo()
            req : std.Counter()
            req.integer > foo.in
            foo.a > snk1.token
            foo.b > snk2.token
        """
        app_info, errors, warnings = compiler.compile(script, "test32")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.1)

        snk1 = d.actor_map['test32:snk1']
        snk2 = d.actor_map['test32:snk2']
        actual1 = utils.report(self.rt1, snk1)
        actual2 = utils.report(self.rt1, snk2)
        expected = list(range(1, 10))

        self.assert_lists_equal(expected, actual1)
        self.assert_lists_equal(expected, actual2)

        d.destroy()



@pytest.mark.essential
class TestNullPorts(CalvinTestBase):

    def testVoidActor(self):
        # Verify that the null port of a std.Void actor behaves as expected
        _log.analyze("TESTRUN", "+", {})
        script = """
            src1 : std.Counter()
            src2 : std.Void()
            join : std.Join()
            snk  : io.StandardOut(store_tokens=1, quiet=1)

            src1.integer > join.token_1
            src2.void > join.token_2
            join.token > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testVoidActor")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.4)

        snk = d.actor_map['testVoidActor:snk']
        actual = utils.report(self.rt1, snk)
        expected = list(range(1, 10))

        self.assert_lists_equal(expected, actual)

        d.destroy()

    def testTerminatorActor(self):
        # Verify that the null port of a std.Terminator actor behaves as expected
        _log.analyze("TESTRUN", "+", {})
        script = """
            src  : std.Counter()
            term : std.Terminator()
            snk  : io.StandardOut(store_tokens=1, quiet=1)

            src.integer > term.void
            src.integer > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testTerminatorActor")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.5)

        snk = d.actor_map['testTerminatorActor:snk']
        actual = utils.report(self.rt1, snk)
        expected = list(range(1, 10))

        self.assert_lists_equal(expected, actual)

        d.destroy()

@pytest.mark.essential
class TestCompare(CalvinTestBase):

    def testBadOp(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src   : std.Counter()
            const : std.Constant(data=5, n=-1)
            pred  : std.Compare(op="<>")
            snk   : io.StandardOut(store_tokens=1, quiet=1)

            src.integer > pred.a
            const.token > pred.b
            pred.result > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testBadOp")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.05)

        snk = d.actor_map['testBadOp:snk']
        actual = utils.report(self.rt1, snk)
        expected = [0] * 10

        self.assert_lists_equal(expected, actual)

        d.destroy()

    def testEqual(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src   : std.Counter()
            const : std.Constant(data=5, n=-1)
            pred  : std.Compare(op="=")
            snk   : io.StandardOut(store_tokens=1, quiet=1)

            src.integer > pred.a
            const.token > pred.b
            pred.result > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testEqual")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.1)

        snk = d.actor_map['testEqual:snk']
        actual = utils.report(self.rt1, snk)
        expected = [x == 5 for x in range(1, 10)]

        self.assert_lists_equal(expected, actual)

        d.destroy()

    def testGreaterThanOrEqual(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src   : std.Counter()
            const : std.Constant(data=5, n=-1)
            pred  : std.Compare(op=">=")
            snk   : io.StandardOut(store_tokens=1, quiet=1)

            src.integer > pred.a
            const.token > pred.b
            pred.result > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testGreaterThanOrEqual")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.1)

        snk = d.actor_map['testGreaterThanOrEqual:snk']
        actual = utils.report(self.rt1, snk)
        expected = [x >= 5 for x in range(1, 10)]

        self.assert_lists_equal(expected, actual)

        d.destroy()


@pytest.mark.essential
class TestSelect(CalvinTestBase):

    def testTrue(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src   : std.Counter()
            const : std.Constant(data=true, n=-1)
            route : std.Select()
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            term  : std.Terminator()

            src.integer > route.data
            const.token > route.select
            route.case_true  > snk.token
            route.case_false > term.void
        """
        app_info, errors, warnings = compiler.compile(script, "testTrue")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.2)

        snk = d.actor_map['testTrue:snk']
        actual = utils.report(self.rt1, snk)
        expected = list(range(1, 10))

        self.assert_lists_equal(expected, actual)

        d.destroy()

    def testFalse(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src   : std.Counter()
            const : std.Constant(data=0, n=-1)
            route : std.Select()
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            term  : std.Terminator()

            src.integer > route.data
            const.token > route.select
            route.case_true  > term.void
            route.case_false > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testFalse")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.5)

        snk = d.actor_map['testFalse:snk']
        actual = utils.report(self.rt1, snk)
        expected = list(range(1, 10))

        self.assert_lists_equal(expected, actual)

        d.destroy()

    def testBadSelect(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src   : std.Counter()
            const : std.Constant(data=2, n=-1)
            route : std.Select()
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            term  : std.Terminator()

            src.integer > route.data
            const.token > route.select
            route.case_true  > term.void
            route.case_false > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testBadSelect")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.5)

        snk = d.actor_map['testBadSelect:snk']
        actual = utils.report(self.rt1, snk)
        expected = list(range(1, 10))

        self.assert_lists_equal(expected, actual)

        d.destroy()


@pytest.mark.essential
class TestDeselect(CalvinTestBase):

    def testDeselectTrue(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src     : std.Counter()
            const_5 : std.Constantify(constant=5)
            const_0 : std.Constant(data=0, n=-1)
            const_1 : std.Constant(data=1, n=-1)
            comp    : std.Compare(op="<=")
            ds      : std.Deselect()
            snk     : io.StandardOut(store_tokens=1, quiet=1)

            const_0.token > ds.case_false
            const_1.token > ds.case_true
            src.integer > comp.a
            src.integer > const_5.in
            const_5.out > comp.b
            comp.result > ds.select
            ds.data > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testDeselectTrue")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.5)

        snk = d.actor_map['testDeselectTrue:snk']
        actual = utils.report(self.rt1, snk)
        expected = [1] * 5 + [0] * 5

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()

    def testDeselectFalse(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src     : std.Counter()
            const_5 : std.Constantify(constant=5)
            const_0 : std.Constant(data=0, n=-1)
            const_1 : std.Constant(data=1, n=-1)
            comp    : std.Compare(op="<=")
            ds      : std.Deselect()
            snk     : io.StandardOut(store_tokens=1, quiet=1)

            const_0.token > ds.case_true
            const_1.token > ds.case_false
            src.integer > comp.a
            src.integer > const_5.in
            const_5.out > comp.b
            comp.result > ds.select
            ds.data > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testDeselectFalse")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.5)

        snk = d.actor_map['testDeselectFalse:snk']
        actual = utils.report(self.rt1, snk)
        expected = [0] * 5 + [1] * 5

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()

    def testDeselectBadSelect(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src     : std.Counter()
            const_5 : std.Constantify(constant=5)
            const_0 : std.Constant(data=0, n=11)
            ds      : std.Deselect()
            snk     : io.StandardOut(store_tokens=1, quiet=1)

            const_0.token > ds.case_false
            src.integer > ds.case_true
            const_0.token > const_5.in
            const_5.out > ds.select
            ds.data > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testDeselectBadSelect")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.5)

        snk = d.actor_map['testDeselectBadSelect:snk']
        actual = utils.report(self.rt1, snk)
        expected = [0] * 10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()


@pytest.mark.essential
class TestLineJoin(CalvinTestBase):

    def testBasicJoin(self):
        _log.analyze("TESTRUN", "+", {})
        datafile = absolute_filename('data.txt')
        script = """
            fname : std.Constant(data="%s")
            src   : io.FileReader()
            join  : text.LineJoin()
            snk   : io.StandardOut(store_tokens=1, quiet=1)

            fname.token > src.filename
            src.out   > join.line
            join.text > snk.token
        """ % (datafile, )
        app_info, errors, warnings = compiler.compile(script, "testBasicJoin")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(1)

        snk = d.actor_map['testBasicJoin:snk']
        actual = utils.report(self.rt1, snk)
        with open(datafile, "r") as fp:
            expected = ["\n".join([l.rstrip() for l in fp.readlines()])]

        self.assert_lists_equal(expected, actual, min_length=1)

        d.destroy()

    @pytest.mark.xfail
    def testCustomTriggerJoin(self):
        _log.analyze("TESTRUN", "+", {})
        datafile = absolute_filename('data.txt')
        script = """
            fname : std.Constant(data="%s")
            src   : io.FileReader()
            join  : text.LineJoin()
            snk   : io.StandardOut(store_tokens=1, quiet=1)

            fname.token > src.filename
            src.out   > join.line
            join.text > snk.token
        """ % (datafile, )
        app_info, errors, warnings = compiler.compile(script, "testCustomTriggerJoin")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.5)

        snk = d.actor_map['testCustomTriggerJoin:snk']
        actual = utils.report(self.rt1, snk)
        with open(datafile, "r") as fp:
            expected = [l.rstrip() for l in fp.readlines()]
            expected = ['\n'.join(expected[:4]), '\n'.join(expected[4:])]

        self.assert_lists_equal(expected, actual, min_length=2)

        d.destroy()

    @pytest.mark.xfail
    def testEmptyStringTriggerJoin(self):
        _log.analyze("TESTRUN", "+", {})
        datafile = absolute_filename('data.txt')
        script = """
            fname : std.Constant(data="%s")
            src   : io.FileReader()
            join  : text.LineJoin()
            snk   : io.StandardOut(store_tokens=1, quiet=1)

            fname.token > src.filename
            src.out   > join.line
            join.text > snk.token
        """ % (datafile, )
        app_info, errors, warnings = compiler.compile(script, "testCustomTriggerJoin")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(0.5)

        snk = d.actor_map['testCustomTriggerJoin:snk']
        actual = utils.report(self.rt1, snk)
        with open(datafile, "r") as fp:
            expected = [l.rstrip() for l in fp.readlines()]
            expected = ['\n'.join(expected[:10]), '\n'.join(expected[10:])]

        self.assert_lists_equal(expected, actual, min_length=2)

        d.destroy()



@pytest.mark.essential
class TestRegex(CalvinTestBase):

    def testRegexMatch(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src   : std.Constant(data="24.1632", n=1)
            regex : text.RegexMatch(regex=!"\d+\.\d+")
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            term  : std.Terminator()

            src.token      > regex.text
            regex.match    > snk.token
            regex.no_match > term.void
        """
        app_info, errors, warnings = compiler.compile(script, "testRegexMatch")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testRegexMatch:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["24.1632"]

        self.assert_lists_equal(expected, actual, min_length=1)

        d.destroy()


    def testRegexNoMatch(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src   : std.Constant(data="x24.1632", n=1)
            regex : text.RegexMatch(regex=!"\d+\.\d+")
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            term  : std.Terminator()

            src.token      > regex.text
            regex.no_match > snk.token
            regex.match    > term.void
        """
        app_info, errors, warnings = compiler.compile(script, "testRegexNoMatch")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testRegexNoMatch:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["x24.1632"]

        self.assert_lists_equal(expected, actual, min_length=1)

        d.destroy()

    def testRegexCapture(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src   : std.Constant(data="24.1632", n=1)
            regex : text.RegexMatch(regex=!"(\d+)\.\d+")
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            term  : std.Terminator()

            src.token      > regex.text
            regex.match    > snk.token
            regex.no_match > term.void
        """
        app_info, errors, warnings = compiler.compile(script, "testRegexCapture")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testRegexCapture:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["24"]

        self.assert_lists_equal(expected, actual, min_length=1)

        d.destroy()

    def testRegexMultiCapture(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src   : std.Constant(data="24.1632", n=1)
            regex : text.RegexMatch(regex=!"(\d+)\.(\d+)")
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            term  : std.Terminator()

            src.token      > regex.text
            regex.match    > snk.token
            regex.no_match > term.void
        """
        app_info, errors, warnings = compiler.compile(script, "testRegexMultiCapture")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testRegexMultiCapture:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["24"]

        self.assert_lists_equal(expected, actual, min_length=1)

        d.destroy()


    def testRegexCaptureNoMatch(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            src   : std.Constant(data="x24.1632", n=1)
            regex : text.RegexMatch(regex=!"(\d+)\.\d+")
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            term  : std.Terminator()

            src.token      > regex.text
            regex.no_match > snk.token
            regex.match    > term.void
        """
        app_info, errors, warnings = compiler.compile(script, "testRegexCaptureNoMatch")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testRegexCaptureNoMatch:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["x24.1632"]

        self.assert_lists_equal(expected, actual, min_length=1)

        d.destroy()

@pytest.mark.essential
class TestConstantAsArguments(CalvinTestBase):

    def testConstant(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            define FOO = 42
            src   : std.Constant(data=FOO, n=10)
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            src.token > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testConstant")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testConstant:snk']
        actual = utils.report(self.rt1, snk)
        expected = [42]*10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()

    def testConstantRecursive(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            define FOO = BAR
            define BAR = 42
            src   : std.Constant(data=FOO, n=10)
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            src.token > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testConstantRecursive")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testConstantRecursive:snk']
        actual = utils.report(self.rt1, snk)
        expected = [42]*10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()


@pytest.mark.essential
class TestConstantOnPort(CalvinTestBase):

    def testLiteralOnPort(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            42 > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testLiteralOnPort")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testLiteralOnPort:snk']
        actual = utils.report(self.rt1, snk)
        expected = [42]*10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()

    def testConstantOnPort(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            define FOO = "Hello"
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            FOO > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testConstantOnPort")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testConstantOnPort:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["Hello"]*10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()

    def testConstantRecursiveOnPort(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            define FOO = BAR
            define BAR = "yay"
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            FOO > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testConstantRecursiveOnPort")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testConstantRecursiveOnPort:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["yay"]*10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()


@pytest.mark.essential
class TestConstantAndComponents(CalvinTestBase):

    def testLiteralOnCompPort(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            component Foo() -> out {
                i:std.Stringify()
                42 > i.in
                i.out > .out
            }
            src   : Foo()
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            src.out > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testLiteralOnCompPort")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testLiteralOnCompPort:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["42"]*10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()

    def testConstantOnCompPort(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            define MEANING = 42
            component Foo() -> out {
                i:std.Stringify()
                MEANING > i.in
                i.out > .out
            }
            src   : Foo()
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            src.out > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testConstantOnCompPort")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testConstantOnCompPort:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["42"]*10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()

    def testStringConstantOnCompPort(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
            define MEANING = "42"
            component Foo() -> out {
                i:std.Identity()
                MEANING > i.token
                i.token > .out
            }
            src   : Foo()
            snk   : io.StandardOut(store_tokens=1, quiet=1)
            src.out > snk.token
        """
        app_info, errors, warnings = compiler.compile(script, "testStringConstantOnCompPort")
        print errors
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testStringConstantOnCompPort:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["42"]*10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()

@pytest.mark.essential
class TestConstantAndComponentsArguments(CalvinTestBase):

    def testComponentArgument(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
        component Count(len) -> seq {
            src : std.Constant(data="hup", n=len)
            src.token > .seq
        }
        src : Count(len=5)
        snk : io.StandardOut(store_tokens=1, quiet=1)
        src.seq > snk.token
        """

        app_info, errors, warnings = compiler.compile(script, "testComponentArgument")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testComponentArgument:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["hup"]*5

        self.assert_lists_equal(expected, actual, min_length=5)

        d.destroy()

    def testComponentConstantArgument(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
        define FOO = 5
        component Count(len) -> seq {
            src : std.Constant(data="hup", n=len)
            src.token > .seq
        }
        src : Count(len=FOO)
        snk : io.StandardOut(store_tokens=1, quiet=1)
        src.seq > snk.token
        """

        app_info, errors, warnings = compiler.compile(script, "testComponentConstantArgument")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testComponentConstantArgument:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["hup"]*5

        self.assert_lists_equal(expected, actual, min_length=5)

        d.destroy()



    def testComponentConstantArgumentDirect(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
        define FOO = 10
        component Count() -> seq {
         src : std.Constant(data="hup", n=FOO)
         src.token > .seq
        }
        src : Count()
        snk : io.StandardOut(store_tokens=1, quiet=1)
        src.seq > snk.token
        """

        app_info, errors, warnings = compiler.compile(script, "testComponentConstantArgumentDirect")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testComponentConstantArgumentDirect:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["hup"]*10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()


    def testComponentArgumentAsImplicitActor(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
        component Count(data) -> seq {
            i : std.Identity()
            data > i.token
            i.token > .seq
        }
        src : Count(data="hup")
        snk : io.StandardOut(store_tokens=1, quiet=1)
        src.seq > snk.token
        """

        app_info, errors, warnings = compiler.compile(script, "testComponentArgumentAsImplicitActor")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testComponentArgumentAsImplicitActor:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["hup"]*10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()


    def testComponentConstantArgumentAsImplicitActor(self):
        _log.analyze("TESTRUN", "+", {})
        script = """
        define FOO = "hup"
        component Count(data) -> seq {
            i : std.Identity()
            data > i.token
            i.token > .seq
        }
        src : Count(data=FOO)
        snk : io.StandardOut(store_tokens=1, quiet=1)
        src.seq > snk.token
        """

        app_info, errors, warnings = compiler.compile(script, "testComponentConstantArgumentAsImplicitActor")
        d = deployer.Deployer(self.rt1, app_info)
        d.deploy()
        time.sleep(.1)

        snk = d.actor_map['testComponentConstantArgumentAsImplicitActor:snk']
        actual = utils.report(self.rt1, snk)
        expected = ["hup"]*10

        self.assert_lists_equal(expected, actual, min_length=10)

        d.destroy()
