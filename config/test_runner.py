import logging

from django.test.runner import DiscoverRunner


class QuietLogRunner(DiscoverRunner):
    """Keeps the console log handler quiet while tests run.

    The app logs to the console (CloudWatch picks it up on AWS), so without this
    every refused request in the tests would print a warning. Loggers still run,
    so assertLogs works; only the console output is silenced.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._console = logging.getHandlerByName("console")
        if self._console is not None:
            self._console_level = self._console.level
            self._console.setLevel(logging.CRITICAL + 1)

    def teardown_test_environment(self, **kwargs):
        if self._console is not None:
            self._console.setLevel(self._console_level)
        super().teardown_test_environment(**kwargs)
