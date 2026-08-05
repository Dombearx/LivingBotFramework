from livingbot.directory import Directory


def test_name_for_known_user_returns_their_display_name() -> None:
    directory = Directory({"42": "Kuba"})

    result = directory.name_for("42")

    assert result == "Kuba"


def test_name_for_unknown_user_falls_back_to_a_labelled_id() -> None:
    directory = Directory({})

    result = directory.name_for("42")

    assert result == "User 42"


def test_id_for_known_name_returns_the_user_id() -> None:
    directory = Directory({"42": "Kuba"})

    result = directory.id_for("Kuba")

    assert result == "42"


def test_id_for_ignores_a_leading_at_sign() -> None:
    directory = Directory({"42": "Kuba"})

    result = directory.id_for("@Kuba")

    assert result == "42"


def test_id_for_matches_regardless_of_case() -> None:
    directory = Directory({"42": "Kuba"})

    result = directory.id_for("kuba")

    assert result == "42"


def test_id_for_unknown_name_returns_none() -> None:
    directory = Directory({"42": "Kuba"})

    result = directory.id_for("Zenon")

    assert result is None


def test_to_mentions_replaces_a_name_with_a_pingable_mention() -> None:
    directory = Directory({"42": "Kuba"})

    result = directory.to_mentions("hej @Kuba, idziesz?")

    assert result == "hej <@42>, idziesz?"


def test_to_mentions_leaves_an_unknown_name_alone() -> None:
    directory = Directory({"42": "Kuba"})

    result = directory.to_mentions("hej @Zenon, idziesz?")

    assert result == "hej @Zenon, idziesz?"


def test_to_mentions_leaves_the_name_alone_without_an_at_sign() -> None:
    directory = Directory({"42": "Kuba"})

    result = directory.to_mentions("Kuba już poszedł")

    assert result == "Kuba już poszedł"


def test_to_mentions_prefers_the_longer_name_when_one_prefixes_another() -> None:
    directory = Directory({"1": "Jack", "2": "Jack Black"})

    result = directory.to_mentions("@Jack Black wpadł")

    assert result == "<@2> wpadł"


def test_to_mentions_does_not_match_a_name_that_only_prefixes_a_longer_word() -> None:
    directory = Directory({"1": "Jack"})

    result = directory.to_mentions("@Jackson wpadł")

    assert result == "@Jackson wpadł"
