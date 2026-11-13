from eval import robustness


def test_every_awkward_or_hostile_resume_behaves_as_expected(capsys):
    # the table it prints is the evidence. a failure shows up there, so print it when the test fails
    code = robustness.main()
    out = capsys.readouterr().out
    assert code == 0, out
