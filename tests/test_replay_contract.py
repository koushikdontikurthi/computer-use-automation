from app.models import ResultStatus, RunResult


def test_result_contract_separates_business_outcome():
    result = RunResult(status=ResultStatus.business_outcome, business_code="MEMBER_NOT_FOUND")
    assert result.status.value == "business_outcome"
    assert result.business_code == "MEMBER_NOT_FOUND"
