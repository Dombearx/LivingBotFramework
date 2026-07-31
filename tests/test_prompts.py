from livingbot.prompts import build_scheduled_post_trigger


def test_build_scheduled_post_trigger_includes_the_topic() -> None:
    result = build_scheduled_post_trigger("her new gym shoes")

    assert "her new gym shoes" in result


def test_build_scheduled_post_trigger_differs_per_topic() -> None:
    first = build_scheduled_post_trigger("her new gym shoes")
    second = build_scheduled_post_trigger("the trip to the mountains")

    assert first != second
