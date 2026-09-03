from scripts.data.a2_output_matcher import outputs_match, parse_output


def test_exact_and_horizontal_whitespace_match() -> None:
    assert outputs_match("answer  1\n", "answer\t1", "p00001")


def test_line_structure_remains_strict() -> None:
    assert not outputs_match("1\n2\n", "1 2\n", "p00001")


def test_default_absolute_float_tolerance() -> None:
    assert outputs_match("1.00000", "1.00009", "p00001")
    assert not outputs_match("1.00000", "1.00011", "p00001")


def test_problem_specific_float_tolerance() -> None:
    assert outputs_match("0.9920625\n", "0.992062500000\n", "p03043")
    assert not outputs_match("1.0", "1.000000002", "p03043")


def test_representative_a2_precision_differences_match() -> None:
    examples = [
        ("p03776", "28.00000000\n1\n", "28.0000000000\n1"),
        ("p03169", "54.48064457488221", "54.4806445749\n"),
        ("p02380", "0.694658370459\n4.4569285496\n", "0.6946583705\n4.4569285496\n"),
        ("p02884", "2.65942857143\n", "2.659428571428571253"),
    ]
    for problem_id, expected, actual in examples:
        assert outputs_match(expected, actual, problem_id)


def test_non_numeric_tokens_remain_exact() -> None:
    assert not outputs_match("YES", "Yes", "p00001")


def test_numeric_prefix_semantics_match_legacy_parser() -> None:
    assert len(parse_output("1e-3")[0]) == 2
