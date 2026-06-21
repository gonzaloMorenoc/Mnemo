from src.ingest.detect import detect_source

ALLURE = b'[{"name": "t", "status": "failed", "statusDetails": {"message": "x"}}]'
JUNIT = b'<testsuites><testsuite><testcase name="t"><failure>x</failure></testcase></testsuite></testsuites>'
TESTNG = b'<testng-results><suite/></testng-results>'
ROBOT = b'<robot><suite/></robot>'
CUCUMBER = b'[{"keyword": "Feature", "name": "F", "elements": []}]'
PLAYWRIGHT = b'{"config": {}, "suites": [], "stats": {}}'
CYPRESS = b'{"stats": {}, "results": []}'


def test_detect_each_format():
    assert detect_source(ALLURE) == "allure"
    assert detect_source(JUNIT) == "junit"
    assert detect_source(TESTNG) == "testng"
    assert detect_source(ROBOT) == "robot"
    assert detect_source(CUCUMBER) == "cucumber"
    assert detect_source(PLAYWRIGHT) == "playwright"
    assert detect_source(CYPRESS) == "cypress"


def test_detect_garbage_returns_none():
    assert detect_source(b"this is not a report") is None
    assert detect_source(b"") is None


def test_detect_unknown_xml_returns_none():
    assert detect_source(b"<unknown><x/></unknown>") is None
