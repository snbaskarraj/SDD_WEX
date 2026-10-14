def test_health_reports_the_portfolio(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["as_of"] == "2026-09-30"
    assert body["semantic_version"] == "1"
    assert body["rows"]["transactions"] == 5214
    assert body["rows"]["customers"] == 37


def test_catalog_lists_metrics_and_examples(client):
    response = client.get("/api/catalog")
    assert response.status_code == 200
    body = response.json()
    labels = {metric["label"] for metric in body["metrics"]}
    assert "Fuel spend" in labels
    assert "Delinquency rate" in labels
    assert any(item["question"].startswith("Top 5") for item in body["examples"])


def test_blank_question_is_400_and_unknown_field_is_422(client):
    blank = client.post("/api/ask", json={"question": "   "})
    assert blank.status_code == 400
    extra = client.post("/api/ask", json={"question": "fuel spend", "engine": "sql"})
    assert extra.status_code == 422


def test_ask_returns_sql_rows_and_a_session(client):
    response = client.post("/api/ask", json={"question": "Total fuel spend this year"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answer"
    assert body["spec"]["metric"] == "fuel_spend"
    assert body["spec"]["time_range"]["label"] == "this year"
    assert "SELECT" in body["sql"]
    assert "DROP" not in body["sql"]
    assert body["rows"][0]["value"] > 0
    assert body["highlight"]["kind"] == "total"
    assert body["session_id"]


def test_off_topic_is_a_clarification(client):
    response = client.post("/api/ask", json={"question": "What's the weather in Dallas?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "clarify"
    assert body["rows"] == []
    assert body["suggestions"]


def test_follow_up_round_trip(client):
    first = client.post("/api/ask", json={"question": "Fuel spend by region this year"})
    session = first.json()["session_id"]
    second = client.post("/api/ask", json={"question": "and for Texas", "session_id": session})
    body = second.json()
    assert body["status"] == "answer"
    assert body["spec"]["filters"] == [{"dimension": "merchant_state", "values": ["Texas"]}]
    assert body["spec"]["group_by"] == []
    assert body["spec"]["metric"] == "fuel_spend"


def test_home_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Fleetline" in response.text
