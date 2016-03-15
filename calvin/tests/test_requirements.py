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

import unittest
import time
import multiprocessing
from calvin.runtime.north import calvin_node
from calvin.Tools import cscompiler as compiler
from calvin.Tools import deployer
import pytest
from calvin.utilities import utils
from calvin.utilities.nodecontrol import dispatch_node, dispatch_storage_node
from calvin.utilities import calvinuuid
from warnings import warn
from calvin.utilities.attribute_resolver import format_index_string
import socket
import os
import json
from calvin.utilities import calvinlogger
from calvin.utilities import calvinconfig

_log = calvinlogger.get_logger(__name__)
_conf = calvinconfig.get()

try:
    ip_addr = os.environ["CALVIN_TEST_LOCALHOST"]
except:
    import socket
    ip_addr = socket.gethostbyname(socket.gethostname())

rt1 = None
rt2 = None
rt3 = None
test_script_dir = None

def absolute_filename(filename):
    import os.path
    return os.path.join(os.path.dirname(__file__), filename)


@pytest.mark.slow
class TestDeployScript(unittest.TestCase):

    @pytest.fixture(autouse=True, scope="class")
    def setup(self, request):
        global rt1
        global rt2
        global rt3
        global test_script_dir
        rt1, _ = dispatch_node("calvinip://%s:5000" % (ip_addr,), "http://%s:5003" % ip_addr,
             attributes={'indexed_public':
                  {'owner':{'organization': 'org.testexample', 'personOrGroup': 'testOwner1'},
                   'node_name': {'organization': 'org.testexample', 'name': 'testNode1'},
                   'address': {'country': 'SE', 'locality': 'testCity', 'street': 'testStreet', 'streetNumber': 1}}})
        time.sleep(1)  # Less storage operations are droped if we wait a bit
        rt2, _ = dispatch_node("calvinip://%s:5001" % (ip_addr,), "http://%s:5004" % ip_addr,
             attributes={'indexed_public':
                  {'owner':{'organization': 'org.testexample', 'personOrGroup': 'testOwner1'},
                   'node_name': {'organization': 'org.testexample', 'name': 'testNode2'},
                   'address': {'country': 'SE', 'locality': 'testCity', 'street': 'testStreet', 'streetNumber': 1}}})
        time.sleep(1)  # Less storage operations are droped if we wait a bit
        rt3, _ = dispatch_node("calvinip://%s:5002" % (ip_addr,), "http://%s:5005" % ip_addr,
             attributes={'indexed_public':
                  {'owner':{'organization': 'org.testexample', 'personOrGroup': 'testOwner2'},
                   'node_name': {'organization': 'org.testexample', 'name': 'testNode3'},
                   'address': {'country': 'SE', 'locality': 'testCity', 'street': 'testStreet', 'streetNumber': 2}}})
        time.sleep(1)  # Less storage operations are droped if we wait a bit

        test_script_dir = absolute_filename('scripts/')
        request.addfinalizer(self.teardown)

    def teardown(self):
        global rt1
        global rt2
        global rt3
        utils.quit(rt1)
        utils.quit(rt2)
        utils.quit(rt3)
        time.sleep(0.2)
        for p in multiprocessing.active_children():
            p.terminate()
        time.sleep(0.2)

    def verify_storage(self):
        global rt1
        global rt2
        global rt3
        rt1_id = utils.get_node_id(rt1)
        rt2_id = utils.get_node_id(rt2)
        rt3_id = utils.get_node_id(rt3)
        assert rt1_id
        assert rt2_id
        assert rt3_id
        print "RUNTIMES:", rt1_id, rt2_id, rt3_id
        #caps = utils.get_index(rt1, 'node/capabilities/calvinsys.events.timer')
        #assert set(caps['result']) >= set([rt1_id, rt2_id, rt3_id])
        #caps = utils.get_index(rt2, 'node/capabilities/calvinsys.events.timer')
        #assert set(caps['result']) >= set([rt1_id, rt2_id, rt3_id])
        #caps = utils.get_index(rt3, 'node/capabilities/calvinsys.events.timer')
        #assert set(caps['result']) >= set([rt1_id, rt2_id, rt3_id])
        assert utils.get_index(rt2, format_index_string(['node_name', {'organization': 'org.testexample', 'name': 'testNode1'}]))
        assert utils.get_index(rt3, format_index_string(['node_name', {'organization': 'org.testexample', 'name': 'testNode1'}]))
        assert utils.get_index(rt1, format_index_string(['node_name', {'organization': 'org.testexample', 'name': 'testNode2'}]))
        assert utils.get_index(rt3, format_index_string(['node_name', {'organization': 'org.testexample', 'name': 'testNode2'}]))
        assert utils.get_index(rt1, format_index_string(['node_name', {'organization': 'org.testexample', 'name': 'testNode3'}]))
        assert utils.get_index(rt2, format_index_string(['node_name', {'organization': 'org.testexample', 'name': 'testNode3'}]))

    @pytest.mark.slow
    def testDeploySimple(self):
        _log.analyze("TESTRUN", "+", {})
        self.verify_storage()
        
        from calvin.Tools.cscontrol import control_deploy as deploy_app
        from collections import namedtuple
        DeployArgs = namedtuple('DeployArgs', ['node', 'attr', 'script','reqs', 'check'])
        args = DeployArgs(node='http://%s:5003' % ip_addr,
                          script=open(test_script_dir+"test_deploy1.calvin"), attr=None,
                                reqs=test_script_dir+"test_deploy1.deployjson", check=True)
        result = {}
        try:
            result = deploy_app(args)
        except:
            raise Exception("Failed deployment of app %s, no use to verify if requirements fulfilled" % args.script.name)
        time.sleep(2)
        actors = [utils.get_actors(rt1), utils.get_actors(rt2), utils.get_actors(rt3)]
        # src -> rt2, sum -> rt2, snk -> rt3
        assert result['actor_map']['test_deploy1:src'] in actors[1]
        assert result['actor_map']['test_deploy1:sum'] in actors[1]
        assert result['actor_map']['test_deploy1:snk'] in actors[2]
        utils.delete_application(rt1, result['application_id'])

    @pytest.mark.slow
    def testDeployLongActorChain(self):
        _log.analyze("TESTRUN", "+", {})
        self.verify_storage()

        from calvin.Tools.cscontrol import control_deploy as deploy_app
        from collections import namedtuple
        DeployArgs = namedtuple('DeployArgs', ['node', 'attr', 'script','reqs', 'check'])
        args = DeployArgs(node='http://%s:5003' % ip_addr,
                          script=open(test_script_dir+"test_deploy2.calvin"), attr=None,
                                reqs=test_script_dir+"test_deploy2.deployjson", check=True)
        result = {}
        try:
            result = deploy_app(args)
        except:
            raise Exception("Failed deployment of app %s, no use to verify if requirements fulfilled" % args.script.name)
        time.sleep(2)
        actors = [utils.get_actors(rt1), utils.get_actors(rt2), utils.get_actors(rt3)]
        # src -> rt1, sum[1:8] -> [rt1, rt2, rt3], snk -> rt3
        assert result['actor_map']['test_deploy2:src'] in actors[0]
        assert result['actor_map']['test_deploy2:snk'] in actors[2]
        sum_list=[result['actor_map']['test_deploy2:sum%d'%i] for i in range(1,9)]
        sum_place = [0 if a in actors[0] else 1 if a in actors[1] else 2 if a in actors[2] else -1 for a in sum_list]
        assert not any([p==-1 for p in sum_place])
        assert all(x<=y for x, y in zip(sum_place, sum_place[1:]))
        utils.delete_application(rt1, result['application_id'])

    @pytest.mark.slow
    def testDeployComponent(self):
        _log.analyze("TESTRUN", "+", {})
        self.verify_storage()

        from calvin.Tools.cscontrol import control_deploy as deploy_app
        from collections import namedtuple
        DeployArgs = namedtuple('DeployArgs', ['node', 'attr', 'script','reqs', 'check'])
        args = DeployArgs(node='http://%s:5003' % ip_addr,
                          script=open(test_script_dir+"test_deploy3.calvin"), attr=None,
                                reqs=test_script_dir+"test_deploy3.deployjson", check=True)
        result = {}
        try:
            result = deploy_app(args)
        except:
            raise Exception("Failed deployment of app %s, no use to verify if requirements fulfilled" % args.script.name)
        time.sleep(2)
        actors = [utils.get_actors(rt1), utils.get_actors(rt2), utils.get_actors(rt3)]
        # src:(first, second) -> rt1, sum -> rt2, snk -> rt3
        assert result['actor_map']['test_deploy3:src:first'] in actors[0]
        assert result['actor_map']['test_deploy3:src:second'] in actors[0]
        assert result['actor_map']['test_deploy3:sum'] in actors[1]
        assert result['actor_map']['test_deploy3:snk'] in actors[2]
        utils.delete_application(rt1, result['application_id'])

rt1 = None
rt2 = None
test_script_dir = None

@pytest.mark.slow
class TestDeployShadow(unittest.TestCase):

    @pytest.fixture(autouse=True, scope="class")
    def setup(self, request):
        global rt1
        global rt2
        global test_script_dir
        rt1, _ = dispatch_node("calvinip://%s:5000" % (ip_addr,), "http://%s:5003" % ip_addr,
             attributes={'indexed_public':
                  {'owner':{'organization': 'org.testexample', 'personOrGroup': 'testOwner1'},
                   'node_name': {'organization': 'org.testexample', 'name': 'testNode1'},
                   'address': {'country': 'SE', 'locality': 'testCity', 'street': 'testStreet', 'streetNumber': 1}}})

        # Hack to get different config actorpath in actor store for each runtime and blacklist timers on node2
        # (since dispatch will use the same global)
        # FIXME do it properly
        import calvin.actorstore.store
        import calvin.calvinsys
        import copy
        calvin.actorstore.store._conf = copy.deepcopy(calvin.actorstore.store._conf)
        calvin.actorstore.store._conf.config['global']['actor_paths'] = [absolute_filename('test_store')]
        calvin.calvinsys._conf = copy.deepcopy(calvin.actorstore.store._conf)
        calvin.calvinsys._conf.config['global']['capabilities_blacklist'] = ['calvinsys.events.timer']
        time.sleep(1)  # Less storage operations are droped if we wait a bit
        rt2, _ = dispatch_node("calvinip://%s:5001" % (ip_addr,), "http://%s:5004" % ip_addr,
             attributes={'indexed_public':
                  {'owner':{'organization': 'org.testexample', 'personOrGroup': 'testOwner1'},
                   'node_name': {'organization': 'org.testexample', 'name': 'testNode2'},
                   'address': {'country': 'SE', 'locality': 'testCity', 'street': 'testStreet', 'streetNumber': 1}}})
        time.sleep(1)  # Less storage operations are droped if we wait a bit

        test_script_dir = absolute_filename('scripts/')
        request.addfinalizer(self.teardown)

    def teardown(self):
        global rt1
        global rt2
        utils.quit(rt1)
        utils.quit(rt2)
        time.sleep(0.2)
        for p in multiprocessing.active_children():
            p.terminate()
        time.sleep(0.2)

    def verify_storage(self):
        global rt1
        global rt2
        rt1_id = utils.get_node_id(rt1)
        rt2_id = utils.get_node_id(rt2)
        assert rt1_id
        assert rt2_id
        print "RUNTIMES:", rt1_id, rt2_id
        _log.analyze("TESTRUN", "+ IDS", {})
        caps = utils.get_index(rt1, 'node/capabilities/calvinsys.events.timer')
        assert rt1_id in caps['result']
        _log.analyze("TESTRUN", "+ RT1 CAPS", {})
        caps = utils.get_index(rt2, 'node/capabilities/calvinsys.events.timer')
        assert rt1_id in caps['result']
        _log.analyze("TESTRUN", "+ RT2 CAPS", {})
        assert utils.get_index(rt1, format_index_string(['node_name', {'organization': 'org.testexample', 'name': 'testNode2'}]))
        _log.analyze("TESTRUN", "+ RT1 INDEX", {})
        assert utils.get_index(rt2, format_index_string(['node_name', {'organization': 'org.testexample', 'name': 'testNode1'}]))
        _log.analyze("TESTRUN", "+ RT2 INDEX", {})

    @pytest.mark.slow
    def testDeployShadow(self):
        _log.analyze("TESTRUN", "+", {})
        global rt1
        global rt2
        global test_script_dir

        self.verify_storage()

        from calvin.Tools.cscontrol import control_deploy as deploy_app
        from collections import namedtuple
        DeployArgs = namedtuple('DeployArgs', ['node', 'attr', 'script','reqs', 'check'])
        args = DeployArgs(node='http://%s:5003' % ip_addr,
                          script=open(test_script_dir+"test_shadow1.calvin"), attr=None,
                                reqs=test_script_dir+"test_shadow1.deployjson", check=False)
        result = {}
        try:
            result = deploy_app(args)
        except:
            raise Exception("Failed deployment of app %s, no use to verify if requirements fulfilled" % args.script.name)
        #print "RESULT:", result
        time.sleep(2)

        actors = [utils.get_actors(rt1), utils.get_actors(rt2)]
        # src -> rt1, sum -> rt2, snk -> rt1
        assert result['actor_map']['test_shadow1:src'] in actors[0]
        assert result['actor_map']['test_shadow1:sum'] in actors[1]
        assert result['actor_map']['test_shadow1:snk'] in actors[0]
        
        actual = utils.report(rt1, result['actor_map']['test_shadow1:snk'])
        assert len(actual) > 5
        utils.delete_application(rt1, result['application_id'])

    @pytest.mark.slow
    def testDeployRequiresShadow(self):
        _log.analyze("TESTRUN", "+", {})
        global rt1
        global rt2
        global test_script_dir

        self.verify_storage()

        from calvin.Tools.cscontrol import control_deploy as deploy_app
        from collections import namedtuple
        DeployArgs = namedtuple('DeployArgs', ['node', 'attr', 'script','reqs', 'check'])
        args = DeployArgs(node='http://%s:5003' % ip_addr,
                          script=open(test_script_dir+"test_shadow1.calvin"), attr=None,
                                reqs=test_script_dir+"test_shadow2.deployjson", check=False)
        result = {}
        try:
            result = deploy_app(args)
        except:
            raise Exception("Failed deployment of app %s, no use to verify if requirements fulfilled" % args.script.name)
        #print "RESULT:", result
        time.sleep(2)

        actors = [utils.get_actors(rt1), utils.get_actors(rt2)]
        # src -> rt1, sum -> rt2, snk -> rt1
        assert result['actor_map']['test_shadow1:src'] in actors[0]
        assert result['actor_map']['test_shadow1:sum'] in actors[1]
        assert result['actor_map']['test_shadow1:snk'] in actors[0]
        
        actual = utils.report(rt1, result['actor_map']['test_shadow1:snk'])
        assert len(actual) > 5
        utils.delete_application(rt1, result['application_id'])


@pytest.mark.slow
class TestSepDeployShadow(unittest.TestCase):

    @pytest.fixture(autouse=True, scope="class")
    def setup(self, request):
        from calvin.Tools.csruntime import csruntime
        from conftest import _config_pytest
        global rt1
        global rt2
        global test_script_dir
        _conf.save("/tmp/calvin5000.conf")
        try:
            logfile = _config_pytest.getoption("logfile")+"5000"
            outfile = os.path.join(os.path.dirname(logfile), os.path.basename(logfile).replace("log", "out"))
            if outfile == logfile:
                outfile = None
        except:
            logfile = None
            outfile = None
        csruntime(ip_addr, port=5000, controlport=5003, attr={'indexed_public':
                  {'owner':{'organization': 'org.testexample', 'personOrGroup': 'testOwner1'},
                   'node_name': {'organization': 'org.testexample', 'name': 'testNode1'},
                   'address': {'country': 'SE', 'locality': 'testCity', 'street': 'testStreet', 'streetNumber': 1}}},
                   loglevel=_config_pytest.getoption("loglevel"), logfile=logfile, outfile=outfile,
                   configfile="/tmp/calvin5000.conf")
        rt1 = utils.RT("http://%s:5003" % ip_addr)
        _conf.set('global', 'actor_paths', [absolute_filename('test_store')])
        _conf.set('global', 'capabilities_blacklist', ['calvinsys.events.timer'])
        _conf.save("/tmp/calvin5001.conf")
        try:
            logfile = _config_pytest.getoption("logfile")+"5001"
            outfile = os.path.join(os.path.dirname(logfile), os.path.basename(logfile).replace("log", "out"))
            if outfile == logfile:
                outfile = None
        except:
            logfile = None
            outfile = None
        csruntime(ip_addr, port=5001, controlport=5004, attr={'indexed_public':
                  {'owner':{'organization': 'org.testexample', 'personOrGroup': 'testOwner1'},
                   'node_name': {'organization': 'org.testexample', 'name': 'testNode2'},
                   'address': {'country': 'SE', 'locality': 'testCity', 'street': 'testStreet', 'streetNumber': 1}}},
                   loglevel=_config_pytest.getoption("loglevel"), logfile=logfile, outfile=outfile,
                   configfile="/tmp/calvin5001.conf")
        rt2 = utils.RT("http://%s:5004" % ip_addr)

        test_script_dir = absolute_filename('scripts/')
        request.addfinalizer(self.teardown)

    def teardown(self):
        global rt1
        global rt2
        utils.quit(rt1)
        utils.quit(rt2)
        time.sleep(0.2)
        for p in multiprocessing.active_children():
            p.terminate()
        # They will die eventually (about 5 seconds) in most cases, but this makes sure without wasting time
        os.system("pkill -9 -f -l 'csruntime -n %s -p 5000'" % (ip_addr,))
        os.system("pkill -9 -f -l 'csruntime -n %s -p 5001'" % (ip_addr,))
        time.sleep(0.2)

    def verify_storage(self):
        global rt1
        global rt2
        rt1_id = None
        rt2_id = None
        failed = True
        # Try 10 times waiting for control API to be up and running
        for i in range(10):
            try:
                rt1_id = rt1_id or utils.get_node_id(rt1)
                rt2_id = rt2_id or utils.get_node_id(rt2)
                failed = False
                break
            except:
                time.sleep(0.1)
        assert not failed
        assert rt1_id
        assert rt2_id
        print "RUNTIMES:", rt1_id, rt2_id
        _log.analyze("TESTRUN", "+ IDS", {'waited': 0.1*i})
        failed = True
        # Try 20 times waiting for storage to be connected
        caps1 = []
        caps2 = []
        for i in range(20):
            try:
                if len(caps1) != 2:
                    caps1 = utils.get_index(rt1, "node/capabilities/calvinsys.native.python-json")['result']
                if len(caps2) != 2:
                    caps2 = utils.get_index(rt2, "node/capabilities/calvinsys.native.python-json")['result']
                if len(caps1) == 2 and len(caps2) == 2:
                    failed = False
                    break
                else:
                    time.sleep(0.1)
            except:
                time.sleep(0.1)
        assert not failed
        _log.analyze("TESTRUN", "+ STORAGE", {'waited': 0.1*i})
        # Now check for the values needed by this specific test
        caps = utils.get_index(rt1, 'node/capabilities/calvinsys.events.timer')
        assert rt1_id in caps['result']
        _log.analyze("TESTRUN", "+ RT1 CAPS", {})
        caps = utils.get_index(rt2, 'node/capabilities/calvinsys.events.timer')
        assert rt1_id in caps['result']
        _log.analyze("TESTRUN", "+ RT2 CAPS", {})
        assert utils.get_index(rt1, format_index_string(['node_name', {'organization': 'org.testexample', 'name': 'testNode2'}]))
        _log.analyze("TESTRUN", "+ RT1 INDEX", {})
        assert utils.get_index(rt2, format_index_string(['node_name', {'organization': 'org.testexample', 'name': 'testNode1'}]))
        _log.analyze("TESTRUN", "+ RT2 INDEX", {})

    @pytest.mark.slow
    def testSepDeployShadow(self):
        _log.analyze("TESTRUN", "+", {})
        global rt1
        global rt2
        global test_script_dir

        self.verify_storage()

        from calvin.Tools.cscontrol import control_deploy as deploy_app
        from collections import namedtuple
        DeployArgs = namedtuple('DeployArgs', ['node', 'attr', 'script','reqs', 'check'])
        args = DeployArgs(node='http://%s:5003' % ip_addr,
                          script=open(test_script_dir+"test_shadow1.calvin"), attr=None,
                                reqs=test_script_dir+"test_shadow1.deployjson", check=False)
        result = {}
        try:
            result = deploy_app(args)
        except:
            raise Exception("Failed deployment of app %s, no use to verify if requirements fulfilled" % args.script.name)
        #print "RESULT:", result
        time.sleep(2)

        actors = [utils.get_actors(rt1), utils.get_actors(rt2)]
        # src -> rt1, sum -> rt2, snk -> rt1
        assert result['actor_map']['test_shadow1:src'] in actors[0]
        assert result['actor_map']['test_shadow1:sum'] in actors[1]
        assert result['actor_map']['test_shadow1:snk'] in actors[0]
        
        actual = utils.report(rt1, result['actor_map']['test_shadow1:snk'])
        assert len(actual) > 5
        utils.delete_application(rt1, result['application_id'])

