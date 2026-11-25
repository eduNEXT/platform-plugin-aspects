"""Competency criterion sinks: criterion definitions, and each learner's status per criterion"""

from platform_plugin_aspects.sinks.base_sink import ModelBaseSink
from platform_plugin_aspects.sinks.serializers import (
    CompetencyCriterionSerializer,
    StudentCompetencyCriterionStatusSerializer,
)

# Enough parent hops to reach the course-level group from the leaf groups openedx-core creates
# today (leaf -> course-level). Deeper trees still work: the serializer walks the rest lazily.
_GROUP_PATH = "group__course", "group__parent__course"


class CompetencyCriterionSink(ModelBaseSink):  # pylint: disable=abstract-method
    """
    Sink for the openedx-core CompetencyCriterion model, archived criteria included.

    One row per criterion, with its effective mastery rule. A change to a rule profile re-dumps
    every criterion that uses it (see signals.py), because the rule is resolved at dump time.
    """

    model = "competency_criterion"
    unique_key = "id"
    clickhouse_table_name = "competency_criterion"
    timestamp_field = "time_last_dumped"
    name = "Competency Criterion"
    serializer_class = CompetencyCriterionSerializer

    def get_queryset(self, start_pk=None):
        return (
            super()
            .get_queryset(start_pk)
            .select_related("object_tag", "rule_profile", *_GROUP_PATH)
        )

    def get_object(self, item_id):
        return self.get_queryset().get(id=item_id)


class StudentCompetencyCriterionStatusSink(
    ModelBaseSink
):  # pylint: disable=abstract-method
    """
    Sink for the openedx-core StudentCompetencyCriterionStatus model: a learner's status on one criterion.
    """

    model = "student_competency_criterion_status"
    unique_key = "id"
    clickhouse_table_name = "student_competency_criterion_status"
    timestamp_field = "time_last_dumped"
    name = "Student Competency Criterion Status"
    serializer_class = StudentCompetencyCriterionStatusSerializer

    def get_queryset(self, start_pk=None):
        return (
            super()
            .get_queryset(start_pk)
            .select_related(
                "user",
                "status",
                "criterion__object_tag",
                *(f"criterion__{path}" for path in _GROUP_PATH),
            )
        )

    def get_object(self, item_id):
        return self.get_queryset().get(id=item_id)
