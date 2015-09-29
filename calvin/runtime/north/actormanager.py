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

from calvin.actorstore.store import ActorStore
from calvin.utilities.calvinlogger import get_logger
from calvin.utilities.calvin_callback import CalvinCB

_log = get_logger(__name__)


def log_callback(reply, **kwargs):
    if reply:
        _log.info("%s: %s" % (kwargs['prefix'], reply))


class ActorManager(object):

    """docstring for ActorManager"""

    def __init__(self, node):
        super(ActorManager, self).__init__()
        self.actors = {}
        self.node = node

    def new(self, actor_type, args, state=None, prev_connections=None, connection_list=None, callback=None):
        """
        Instantiate an actor of type 'actor_type'. Parameters are passed in 'args',
        'name' is an optional parameter in 'args', specifying a human readable name.
        Returns actor id on success and raises an exception if anything goes wrong.
        Optionally applies a serialized state to the actor, the supplied args are ignored and args from state
        is used instead.
        Optionally reconnecting the ports, using either
          1) an unmodified connections structure obtained by the connections command supplied as
             prev_connections or,
          2) a mangled list of tuples with (in_node_id, in_port_id, out_node_id, out_port_id) supplied as
             connection_list
        """
        # When renewing (e.g. after migrate) apply the args from the state
        # instead of any directly supplied
        _log.debug("class: %s args: %s state: %s", actor_type, args, state)
        _log.analyze(self.node.id, "+", {'actor_type': actor_type, 'state': state})

        try:
            if state:
                a = self._new_from_state(actor_type, state)
            else:
                a = self._new(actor_type, args)
        except Exception as e:
            _log.exception("Actor creation failed")
            raise(e)

        self.actors[a.id] = a

        self.node.storage.add_actor(a, self.node.id)

        if prev_connections:
            # Convert prev_connections to connection_list format
            connection_list = self._prev_connections_to_connection_list(prev_connections)

        if connection_list:
            # Migrated actor
            self.connect(a.id, connection_list, callback=callback)
        else:
            # Nothing to connect then we are OK
            if callback:
                callback(status='ACK', actor_id=a.id)
            else:
                return a.id

    def _new_actor(self, actor_type, actor_id=None):
        """Return a 'bare' actor of actor_type, raises an exception on failure."""
        (found, is_primitive, class_) = ActorStore().lookup(actor_type)
        if not found or not is_primitive:
            _log.error("Requested actor %s is not available" % (actor_type))
            raise Exception("ERROR_NOT_FOUND")
        try:
            # Create a 'bare' instance of the actor
            a = class_(actor_type, actor_id)
            a._calvinsys = self.node.calvinsys()
            a.check_requirements()
        except Exception as e:
            _log.exception("")
            _log.error("The actor %s(%s) can't be instantiated." % (actor_type, class_.__init__))
            raise(e)
        return a


    def _new(self, actor_type, args):
        """Return an initialized actor in PENDING state, raises an exception on failure."""
        try:
            a = self._new_actor(actor_type)
            # Now that required APIs are attached we can call init() which may use the APIs
            human_readable_name = args.pop('name', '')
            a.name = human_readable_name
            self.node.pm.add_ports_of_actor(a)
            a.init(**args)
            a.setup_complete()
        except Exception as e:
            _log.exception(e)
            raise(e)
        return a


    def _new_from_state(self, actor_type, state):
        """Return an restored actor in PENDING state, raises an exception on failure."""
        try:
            print repr(state)
            a = self._new_actor(actor_type, actor_id=state['id'])
            a.set_state(state)
            self.node.pm.add_ports_of_actor(a)
            a.did_migrate()
            a.setup_complete()
        except Exception as e:
            raise(e)
        return a


    def destroy(self, actor_id):
        # @TOOD - check order here
        a = self.actors[actor_id]
        a.will_end()
        self.node.pm.remove_ports_of_actor(a)
        # @TOOD - insert callback here
        self.node.storage.delete_actor(actor_id)
        del self.actors[actor_id]

    # DEPRECATED: Enabling of an actor is dependent on wether it's connected or not
    def enable(self, actor_id):
        if actor_id in self.actors:
            self.actors[actor_id].enable()

    # DEPRECATED: Disabling of an actor is dependent on wether it's connected or not
    def disable(self, actor_id):
        if actor_id in self.actors:
            self.actors[actor_id].disable()
        else:
            _log.info("!!!FAILED to disable %s", actor_id)

    def migrate(self, actor_id, node_id, callback = None):
        """ Migrate an actor actor_id to peer node node_id """
        if actor_id not in self.actors:
            # Can only migrate actors from our node
            if callback:
                callback(status="NACK")
            return
        if node_id == self.node.id:
            # No need to migrate to ourself
            if callback:
                callback(status="ACK")
            return

        actor = self.actors[actor_id]
        actor._migrating_to = node_id
        actor.will_migrate()
        actor_type = actor._type
        ports = actor.connections(self.node.id)
        # Disconnect ports and continue in _migrate_disconnect
        self.node.pm.disconnect(callback=CalvinCB(self._migrate_disconnected,
                                                  actor=actor,
                                                  actor_type=actor_type,
                                                  ports=ports,
                                                  node_id=node_id,
                                                  callback=callback),
                                actor_id=actor_id)

    def _migrate_disconnected(self, actor, actor_type, ports, node_id, status=None, callback = None, **state):
        """ Actor disconnected, continue migration """
        if status == 'ACK':
            state = actor.state()
            self.destroy(actor.id)
            self.node.proto.actor_new(node_id, callback, actor_type, state, ports)
        else:
            # FIXME handle errors!!!
            if callback:
                callback(status=status)

    def peernew_to_local_cb(self, reply, **kwargs):
        if kwargs['actor_id'] == reply:
            # Managed to setup since new returned same actor id
            self.node.set_local_reply(kwargs['lmsg_id'], "OK")
        else:
            # Just pass on new cmd reply if it failed
            self.node.set_local_reply(kwargs['lmsg_id'], reply)

    def _prev_connections_to_connection_list(self, prev_connections):
        """Convert prev_connection format to connection_list format"""
        cl = []
        for in_port_id, out_id in prev_connections['inports'].iteritems():
            cl.append((self.node.id, in_port_id, out_id[0], out_id[1]))
        for out_port_id, in_list in prev_connections['outports'].iteritems():
            for in_id in in_list:
                cl.append((self.node.id, out_port_id, in_id[0], in_id[1]))
        return cl

    def connect(self, actor_id, connection_list, callback=None):
        """
        Reconnecting the ports can be done using a connection_list
        of tuples (node_id i.e. our id, port_id, peer_node_id, peer_port_id)
        """
        if actor_id not in self.actors:
            return

        peer_port_ids = [c[3] for c in connection_list]

        for node_id, port_id, peer_node_id, peer_port_id in connection_list:
            self.node.pm.connect(port_id=port_id,
                                 peer_node_id=peer_node_id,
                                 peer_port_id=peer_port_id,
                                 callback=CalvinCB(self._actor_connected,
                                                   peer_port_id=peer_port_id,
                                                   actor_id=actor_id,
                                                   peer_port_ids=peer_port_ids,
                                                   _callback=callback))

    def _actor_connected(self, status, peer_port_id, actor_id, peer_port_ids, _callback, **kwargs):
        """ Get called for each of the actor's ports when connecting, but callback should only be called once
            status: 'ACK'/'NACK'
            _callback: original callback
            peer_port_ids: list of port ids kept in context between calls when *changed* by this function,
                           do not replace it
        """
        # Send NACK if not already done it
        if status == "NACK" and peer_port_ids:
            if _callback:
                del peer_port_ids[:]
                _callback(status="NACK", actor_id=actor_id)
        if peer_port_id in peer_port_ids:
            # Remove this port from list
            peer_port_ids.remove(peer_port_id)
            # If all ports done send ACK
            if not peer_port_ids:
                if _callback:
                    _callback(status="ACK", actor_id=actor_id)

    def connections(self, actor_id):
        return self.actors.get(actor_id, None).connections(self.node.id)

    def dump(self, actor_id):
        actor = self.actors.get(actor_id, None)
        if not actor:
            raise Exception("Actor '%s' not found" % (actor_id,))
        _log.debug("-----------")
        _log.debug(actor)
        _log.debug("-----------")

    def set_port_property(self, actor_id, port_type, port_name, port_property, value):
        try:
            actor = self.actors[actor_id]
        except Exception as e:
            _log.exception("Actor '%s' not found" % (actor_id,))
            raise e
        success = actor.set_port_property(port_type, port_name, port_property, value)
        return 'OK' if success else 'FAILURE'

    def actor_type(self, actor_id):
        actor = self.actors.get(actor_id, None)
        return actor._type if actor else 'BAD ACTOR'

    def report(self, actor_id):
        return self.actors.get(actor_id, None).report()

    def enabled_actors(self):
        return [actor for actor in self.actors.values() if actor.enabled()]

    def list_actors(self):
        return self.actors.keys()

