import logging
from ansible.plugins.callback import CallbackBase

LOGGER = logging.getLogger(__name__)


class AnsibleTrackProgress(CallbackBase):
    """Ansible progress callback class """
    def __init__(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)
        self.total_plays = 0
        self.finished_plays = 0
        self.playbook = None
        self.progress = 0

    def run_on_playbook_start(self, playbook):
        self.playbook = playbook._file_name
        LOGGER.debug("Start progress for Playbook [%s]", self.playbook)
        self.total_plays = len(playbook.get_plays())
        LOGGER.debug("Total plays to run: %d", self.total_plays)

    def run_on_playbook_play_start(self, play):
        LOGGER.debug("Started PLAY [%s]", play.get_name())
        self.progress = float(self.finished_plays) / float(self.total_plays)
        LOGGER.debug("Playbook progress %d%%", self.progress * 100.0)
        self.finished_plays += 1

    def run_on_playbook_stats(self, stats):
        self.progress = 1

    def run_on_playbook_task_start(self, task, is_conditional):
        LOGGER.debug("Started TASK [%s]", task.get_name())


class ErrorsCallback(CallbackBase):
    def __init__(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)
        self.failed_results = []

    def run_on_runner_failed(self, result, ignore_errors=False):
        if ignore_errors:
            # collect non-ignored errors
            return
        self.failed_results.append(result)
