"""
Tests for signal handlers.
"""

from unittest.mock import ANY, Mock, patch

from django.db.models.signals import post_save
from django.test import TestCase

from platform_plugin_aspects.signals import (
    on_catalog_pathway_deleted,
    on_catalog_pathway_saved_txn,
    on_competency_criterion_saved_txn,
    on_competency_rule_profile_saved_txn,
    on_externalid_saved_txn,
    on_pathway_enrollment_saved_txn,
    on_student_competency_course_status_saved_txn,
    on_student_competency_criterion_status_saved_txn,
    on_student_competency_status_saved_txn,
    on_user_retirement,
    receive_course_publish,
)
from platform_plugin_aspects.sinks import CatalogPathwayTombstoneSink
from platform_plugin_aspects.sinks.user_retire_sink import UserRetirementSink


class SignalHandlersTestCase(TestCase):
    """
    Test cases for signal handlers.
    """

    @patch("platform_plugin_aspects.tasks.dump_course_to_clickhouse")
    def test_receive_course_publish(self, mock_dump_task):
        """
        Test that receive_course_publish calls dump_course_to_clickhouse.
        """
        sender = Mock()
        course_key = "sample_key"
        receive_course_publish(sender, course_key)

        mock_dump_task.delay.assert_called_once_with(course_key)

    @patch("platform_plugin_aspects.signals.transaction")
    def test_on_externalid_saved(self, mock_transaction):
        """
        Test that on_externalid_saved calls dump_data_to_clickhouse.
        """
        instance = Mock()
        sender = Mock()
        on_externalid_saved_txn(sender, instance)

        mock_transaction.on_commit.assert_called_once()

    @patch("platform_plugin_aspects.signals.transaction")
    def test_on_catalog_pathway_saved(self, mock_transaction):
        """
        Test that on_catalog_pathway_saved_txn defers the dump to on_commit.
        """
        instance = Mock()
        sender = Mock()
        on_catalog_pathway_saved_txn(sender, instance)

        mock_transaction.on_commit.assert_called_once()

    @patch("platform_plugin_aspects.signals.transaction")
    def test_on_pathway_enrollment_saved(self, mock_transaction):
        """
        Test that on_pathway_enrollment_saved_txn defers the dump to on_commit.
        """
        instance = Mock()
        sender = Mock()
        on_pathway_enrollment_saved_txn(sender, instance)

        mock_transaction.on_commit.assert_called_once()

    @patch("platform_plugin_aspects.tasks.dump_data_to_clickhouse")
    @patch("platform_plugin_aspects.signals.transaction")
    def test_on_catalog_pathway_deleted(self, mock_transaction, mock_dump_task):
        """
        Test that on_catalog_pathway_deleted queues the tombstone sink on commit, with the id
        read before Django clears it.
        """
        instance = Mock(id=7)
        on_catalog_pathway_deleted(Mock(), instance)
        instance.id = None

        mock_dump_task.delay.assert_not_called()
        mock_transaction.on_commit.assert_called_once_with(ANY, robust=True)
        mock_transaction.on_commit.call_args.args[0]()

        mock_dump_task.delay.assert_called_once_with(
            sink_module=CatalogPathwayTombstoneSink.__module__,
            sink_name="CatalogPathwayTombstoneSink",
            object_id="7",
        )

    @patch("platform_plugin_aspects.signals.transaction")
    def test_on_student_competency_status_saved(self, mock_transaction):
        """
        Test that on_student_competency_status_saved_txn defers the dump to a robust on_commit.
        """
        instance = Mock()
        sender = Mock()
        on_student_competency_status_saved_txn(sender, instance)

        mock_transaction.on_commit.assert_called_once()
        assert mock_transaction.on_commit.call_args.kwargs == {"robust": True}

    @patch("platform_plugin_aspects.signals.transaction")
    def test_on_student_competency_course_status_saved(self, mock_transaction):
        """
        Test that on_student_competency_course_status_saved_txn defers the dump to a robust on_commit.
        """
        instance = Mock()
        sender = Mock()
        on_student_competency_course_status_saved_txn(sender, instance)

        mock_transaction.on_commit.assert_called_once()
        assert mock_transaction.on_commit.call_args.kwargs == {"robust": True}

    @patch("platform_plugin_aspects.tasks.dump_data_to_clickhouse")
    @patch(
        "platform_plugin_aspects.signals.StudentCompetencyCourseStatusSink.is_enabled"
    )
    @patch("platform_plugin_aspects.signals.transaction")
    def test_course_status_queues_only_enabled_course_level_rows(
        self, mock_transaction, mock_is_enabled, mock_dump_task
    ):
        """
        Test that a course status is queued only when the sink is enabled and the group is course-level.
        """
        mock_transaction.on_commit.side_effect = lambda fn, robust: fn()
        course_row = Mock(id=7, group=Mock(course_id=3))
        root_row = Mock(id=8, group=Mock(course_id=None))

        mock_is_enabled.return_value = False
        on_student_competency_course_status_saved_txn(Mock(), course_row)
        mock_dump_task.delay.assert_not_called()

        mock_is_enabled.return_value = True
        on_student_competency_course_status_saved_txn(Mock(), root_row)
        mock_dump_task.delay.assert_not_called()

        on_student_competency_course_status_saved_txn(Mock(), course_row)
        mock_dump_task.delay.assert_called_once_with(
            sink_module="platform_plugin_aspects.sinks.student_competency_status_sink",
            sink_name="StudentCompetencyCourseStatusSink",
            object_id="7",
        )

    @patch("platform_plugin_aspects.tasks.dump_data_to_clickhouse")
    def test_on_user_retirement(self, mock_dump_task):
        """
        Test that on_user_retirement calls dump_data_to_clickhouse
        """
        instance = Mock()
        sender = Mock()
        on_user_retirement(sender, instance)

        sink = UserRetirementSink(None, None)

        mock_dump_task.delay.assert_called_once_with(
            sink_module=sink.__module__,
            sink_name=sink.__class__.__name__,
            object_id=str(instance.id),
        )


@patch("platform_plugin_aspects.tasks.dump_data_to_clickhouse")
@patch("platform_plugin_aspects.signals.transaction")
class TestCompetencyCriterionSignals(TestCase):
    """
    Test the receivers of the competency criterion sinks.
    """

    def setUp(self):
        patcher = patch(
            "platform_plugin_aspects.sinks.ModelBaseSink.is_enabled",
            return_value=True,
        )
        self.mock_is_enabled = patcher.start()
        self.addCleanup(patcher.stop)

    def test_criterion_saved(self, mock_transaction, mock_dump_task):
        """
        Test a criterion save queues that criterion's dump on commit.
        """
        mock_transaction.on_commit.side_effect = lambda fn, robust: fn()

        on_competency_criterion_saved_txn(Mock(), Mock(id=4))

        mock_dump_task.delay.assert_called_once_with(
            sink_module="platform_plugin_aspects.sinks.competency_criterion_sink",
            sink_name="CompetencyCriterionSink",
            object_id="4",
        )

    def test_criterion_status_saved(self, mock_transaction, mock_dump_task):
        """
        Test a learner criterion status save queues that row's dump on commit.
        """
        mock_transaction.on_commit.side_effect = lambda fn, robust: fn()

        on_student_competency_criterion_status_saved_txn(Mock(), Mock(id=9))

        mock_dump_task.delay.assert_called_once_with(
            sink_module="platform_plugin_aspects.sinks.competency_criterion_sink",
            sink_name="StudentCompetencyCriterionStatusSink",
            object_id="9",
        )

    @patch("platform_plugin_aspects.signals.get_model")
    def test_rule_profile_saved_redumps_its_criteria(
        self, mock_get_model, mock_transaction, mock_dump_task
    ):
        """
        Test a rule profile save queues one dump per criterion that uses the profile.
        """
        mock_transaction.on_commit.side_effect = lambda fn, robust: fn()
        criteria = mock_get_model.return_value.objects.filter.return_value
        criteria.values_list.return_value = [4, 5]

        on_competency_rule_profile_saved_txn(Mock(), Mock(id=1))

        mock_get_model.return_value.objects.filter.assert_called_once_with(
            rule_profile_id=1
        )
        assert [c.kwargs["object_id"] for c in mock_dump_task.delay.call_args_list] == [
            "4",
            "5",
        ]

    def test_nothing_is_queued_when_the_sink_is_disabled(
        self, mock_transaction, mock_dump_task
    ):
        """
        Test a disabled sink queues nothing.
        """
        mock_transaction.on_commit.side_effect = lambda fn, robust: fn()
        self.mock_is_enabled.return_value = False

        on_competency_criterion_saved_txn(Mock(), Mock(id=4))
        on_student_competency_criterion_status_saved_txn(Mock(), Mock(id=9))
        on_competency_rule_profile_saved_txn(Mock(), Mock(id=1))

        mock_dump_task.delay.assert_not_called()


class _RaisedStatusRow:
    """Stand-in sender for an openedx-core status model, which these tests don't install."""


@patch("platform_plugin_aspects.tasks.dump_data_to_clickhouse")
@patch("platform_plugin_aspects.signals.transaction")
class TestRaisedCompetencyStatusIsDumped(TestCase):
    """
    A raised status reaches every competency status sink.

    openedx-core raises a status with a bulk UPDATE, which sends no signal, and then
    sends post_save itself (openedx_learning.applets.cbe.statuses.raise_status). The
    receivers must queue one dump for that send exactly as they do for a create.
    """

    RECEIVERS = {
        "StudentCompetencyStatusSink": on_student_competency_status_saved_txn,
        "StudentCompetencyCourseStatusSink": on_student_competency_course_status_saved_txn,
        "StudentCompetencyCriterionStatusSink": on_student_competency_criterion_status_saved_txn,
    }

    def setUp(self):
        patcher = patch(
            "platform_plugin_aspects.sinks.ModelBaseSink.is_enabled",
            return_value=True,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _send_raise(self, sink_name, instance):
        """Connect the sink's receiver and send post_save the way raise_status does."""
        receiver = self.RECEIVERS[sink_name]
        post_save.connect(receiver, sender=_RaisedStatusRow)
        try:
            post_save.send(
                sender=_RaisedStatusRow,
                instance=instance,
                created=False,
                update_fields=frozenset({"status_id", "modified"}),
                raw=False,
                using="default",
            )
        finally:
            post_save.disconnect(receiver, sender=_RaisedStatusRow)

    def test_raise_queues_one_dump_per_sink(self, mock_transaction, mock_dump_task):
        """
        Test a raise queues exactly one dump of the raised row, for each of the three sinks.
        """
        mock_transaction.on_commit.side_effect = lambda fn, robust: fn()
        # A course-level row, so the course status sink dumps it.
        instance = Mock(id=12, group=Mock(course_id=3))

        for sink_name in self.RECEIVERS:
            with self.subTest(sink=sink_name):
                mock_dump_task.reset_mock()
                self._send_raise(sink_name, instance)
                mock_dump_task.delay.assert_called_once_with(
                    sink_module=ANY, sink_name=sink_name, object_id="12"
                )

    def test_raise_of_a_non_course_level_group_is_not_dumped(
        self, mock_transaction, mock_dump_task
    ):
        """
        Test the course status sink still skips a raised group that isn't course-level.
        """
        mock_transaction.on_commit.side_effect = lambda fn, robust: fn()

        self._send_raise(
            "StudentCompetencyCourseStatusSink", Mock(id=13, group=Mock(course_id=None))
        )

        mock_dump_task.delay.assert_not_called()
