"""
Test the competency criterion sinks and their serializers.
"""

from unittest.mock import Mock, patch

from platform_plugin_aspects.sinks import (
    CompetencyCriterionSink,
    StudentCompetencyCriterionStatusSink,
)
from platform_plugin_aspects.sinks.serializers import (
    CompetencyCriterionSerializer,
    StudentCompetencyCriterionStatusSerializer,
    get_criterion_course_key,
)


def _group(course_key=None, parent=None):
    """Return a mock criteria group, course-level when ``course_key`` is given."""
    group = Mock(course_id=1 if course_key else None, course=Mock(course_key=course_key))
    # Set after construction: "parent" is a reserved Mock() keyword.
    group.parent = parent
    return group


@patch("platform_plugin_aspects.sinks.ModelBaseSink.get_queryset")
def test_criterion_get_queryset(mock_get_queryset):
    """
    Test the criterion sink loads the object tag, rule profile and two group levels with the row.
    """
    CompetencyCriterionSink(None, None).get_queryset()

    mock_get_queryset.return_value.select_related.assert_called_once_with(
        "object_tag", "rule_profile", "group__course", "group__parent__course"
    )


@patch("platform_plugin_aspects.sinks.ModelBaseSink.get_queryset")
def test_criterion_status_get_queryset(mock_get_queryset):
    """
    Test the criterion status sink loads the learner, status, criterion and two group levels.
    """
    StudentCompetencyCriterionStatusSink(None, None).get_queryset()

    mock_get_queryset.return_value.select_related.assert_called_once_with(
        "user",
        "status",
        "criterion__object_tag",
        "criterion__group__course",
        "criterion__group__parent__course",
    )


@patch.object(StudentCompetencyCriterionStatusSink, "get_queryset")
def test_criterion_status_get_object(mock_get_queryset):
    """
    Test a single dump goes through get_queryset.
    """
    result = StudentCompetencyCriterionStatusSink(None, None).get_object(7)

    mock_get_queryset.return_value.get.assert_called_once_with(id=7)
    assert result == mock_get_queryset.return_value.get.return_value


def test_course_key_walks_up_to_the_course_level_group():
    """
    Test the course key comes from the nearest ancestor group with a course run, at any depth.
    """
    course_level = _group("course-v1:Org+C+R", parent=_group())
    leaf = _group(parent=_group(parent=course_level))

    assert get_criterion_course_key(Mock(group=leaf)) == "course-v1:Org+C+R"
    assert get_criterion_course_key(Mock(group=course_level)) == "course-v1:Org+C+R"


def test_course_key_is_empty_without_a_course_level_group():
    """
    Test a criterion under no course-level group gets an empty course key, not an error.
    """
    assert get_criterion_course_key(Mock(group=_group(parent=_group()))) == ""


def test_criterion_fields():
    """
    Test the exact field order: sink inserts are positional, so it is the ClickHouse column order.
    """
    assert CompetencyCriterionSerializer.Meta.fields == [
        "id",
        "uuid",
        "group_id",
        "tag_id",
        "taxonomy_id",
        "object_id",
        "course_key",
        "rule_source",
        "rule_profile_id",
        "rule_type",
        "rule_payload",
        "archived",
        "dump_id",
        "time_last_dumped",
    ]


def test_criterion_status_fields():
    """
    Test the exact field order, and that the learner row carries no rule.
    """
    assert StudentCompetencyCriterionStatusSerializer.Meta.fields == [
        "id",
        "actor_id",
        "criterion_id",
        "tag_id",
        "taxonomy_id",
        "object_id",
        "course_key",
        "status_id",
        "status_name",
        "created",
        "modified",
        "dump_id",
        "time_last_dumped",
    ]


@patch("platform_plugin_aspects.sinks.serializers.get_competency_api")
def test_criterion_rule_comes_from_core(mock_get_competency_api):
    """
    Test the rule fields come from openedx-core's get_effective_rule, called once per criterion.
    """
    mock_get_competency_api.return_value.get_effective_rule.return_value = Mock(
        source="profile",
        rule_profile_id=1,
        rule_type="Grade",
        rule_payload={"value": 0.8, "op": "gte", "scale": "percent"},
    )
    serializer = CompetencyCriterionSerializer()
    criterion = Mock(pk=4, archived=False)

    assert serializer.get_rule_source(criterion) == "profile"
    assert serializer.get_rule_profile_id(criterion) == 1
    assert serializer.get_rule_type(criterion) == "Grade"
    assert (
        serializer.get_rule_payload(criterion)
        == '{"op": "gte", "scale": "percent", "value": 0.8}'
    )
    assert serializer.get_archived(criterion) == 0
    get_effective_rule = mock_get_competency_api.return_value.get_effective_rule
    get_effective_rule.assert_called_once_with(criterion)


@patch("platform_plugin_aspects.sinks.serializers.get_or_create_xapi_actor_id")
def test_criterion_status_actor_id(mock_get_or_create_xapi_actor_id):
    """
    Test the learner is serialized as their xAPI actor id.
    """
    status = Mock()

    actor_id = StudentCompetencyCriterionStatusSerializer().get_actor_id(status)

    assert actor_id == mock_get_or_create_xapi_actor_id.return_value
    mock_get_or_create_xapi_actor_id.assert_called_once_with(status.user)
