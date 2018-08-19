
import json
import logging
import os

from ansible import constants
from ansible import errors
from ansible.executor.playbook_executor import PlaybookExecutor
from ansible.inventory.manager import InventoryManager
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager

import six

from dynamic_ansible.runner import Runner
from dynamic_ansible import exceptions
from dynamic_ansible.callback import (ErrorsCallback,
                                      AnsibleTrackProgress)

LOGGER = logging.getLogger(__name__)


class Namespace(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class APIRunner(Runner):

    def __init__(self, inventory=None, **kwargs):
        super(self.__class__, self).__init__(inventory, **kwargs)
        self._callbacks = []
        self.tqm = None

    def get_progress(self):
        for c in self._callbacks:
            if c.__class__.__name__ == 'AnsibleTrackProgress':
                return c.progress
        return None

    def run_playbook(self, playbook, inventory=None, **kwargs):
        six.moves.reload_module(constants)
        if not os.path.isfile(playbook):
            raise exceptions.FileNotFound(name=playbook)

        if inventory is None:
            inventory = self.inventory

        LOGGER.debug('Running with inventory : %s', inventory)
        LOGGER.debug('Running with playbook: %s', playbook)

        conn_pass = None
        if 'conn_pass' in kwargs:
            conn_pass = kwargs['conn_pass']

        become_pass = None
        if 'become_pass' in kwargs:
            become_pass = kwargs['become_pass']

        passwords = {'conn_pass': conn_pass, 'become_pass': become_pass}

        playbooks = [playbook]

        options = self._build_opt_dict(inventory, **kwargs)
        loader = DataLoader()
        ansible_inventory = InventoryManager(loader=loader, sources=options.inventory)
        variable_manager = VariableManager(loader=loader, inventory=inventory)

        if six.PY2:
            variable_manager.extra_vars = json.loads(
                json.dumps(options.extra_vars))
        else:
            variable_manager.extra_vars = options.extra_vars

        ansible_inventory.subset(options.subset)

        pbex = PlaybookExecutor(
                                playbooks=playbooks,
                                inventory=ansible_inventory,
                                variable_manager=variable_manager,
                                loader=loader,
                                options=options,
                                passwords=passwords)
        self.tqm = pbex._tqm
        errors_callback = ErrorsCallback()
        self.add_callback(errors_callback)
        # There is no public API for adding callbacks, hence we use a private
        # property to add callbacks
        pbex._tqm._callback_plugins.extend(self._callbacks)
        try:
            pbex.run()
        except errors.AnsibleParserError as e:
            raise exceptions.ParsePlaybookError(msg=str(e))
        stats = pbex._tqm._stats
        failed_results = errors_callback.failed_results
        result = self._process_stats(stats, failed_results)
        return result

    def add_callback(self, callback):
        self._callbacks.append(callback)

    def _build_opt_dict(self, inventory, **kwargs):
        args = {
            'check': None, 'listtasks': None, 'listhosts': None,
            'listtags': None, 'syntax': None, 'module_path': None,
            'skip_tags': [], 'ssh_common_args': '',
            'sftp_extra_args': '', 'scp_extra_args': '',
            'ssh_extra_args': '',
            'inventory': inventory,
            'extra_vars': {}, 'subset': constants.DEFAULT_SUBSET,
            'tags': [], 'verbosity': 0,
        }
        args.update(self.custom_opts)
        args.update(kwargs)

        if isinstance(args['tags'], str):
            args['tags'] = args['tags'].split(',')
        elif not isinstance(args['tags'], list):
            raise exceptions.InvalidParameter(name=type(args['tags']).__name__,
                                              param='tag')
        return Namespace(**args)

    @staticmethod
    def _process_stats(stats, failed_results=[]):
        unreachable_hosts = sorted(stats.dark.keys())
        failed_hosts = sorted(stats.failures.keys())
        error_msg = ''
        failed_tasks = []
        if len(unreachable_hosts) > 0:
            tmpl = "Following nodes were unreachable: {0}\n"
            error_msg += tmpl.format(unreachable_hosts)
        for result in failed_results:
            task_name, msg, host = APIRunner._process_task_result(result)
            failed_tasks.append(task_name)
            tmpl = 'Task "{0}" failed on host "{1}" with message: {2}'
            error_msg += tmpl.format(task_name, host, msg)

        return {"error_msg": error_msg, "unreachable_hosts": unreachable_hosts,
                "failed_hosts": failed_hosts, 'failed_tasks': failed_tasks}

    @staticmethod
    def _process_task_result(task):
        result = task._result
        task_obj = task._task
        host = task._host
        if isinstance(result, dict) and 'msg' in result:
            error_msg = result.get('msg')
        else:
            # task result may be an object with multiple results
            msgs = []
            for res in result.get('results', []):
                if isinstance(res, dict) and 'msg' in res:
                    msgs.append(res.get('result'))
            error_msg = ' '.join(msgs)

        return task_obj.get_name(), error_msg, host.get_name()