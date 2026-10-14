from fleetline.catalog import get_catalog


def test_catalog_loads_the_governed_metrics():
    catalog = get_catalog()
    assert catalog.version == "1"
    assert len(catalog.metrics) == 14
    assert "fuel_spend" in catalog.metrics
    assert "delinquency_rate" in catalog.metrics
    assert catalog.examples


def test_synonyms_are_unique():
    catalog = get_catalog()
    metric_synonyms = [syn for metric in catalog.metrics.values() for syn in metric.synonyms]
    dimension_synonyms = [syn for dim in catalog.dimensions.values() for syn in dim.synonyms]
    value_synonyms = [phrase for dim in catalog.dimensions.values() for phrase in dim.value_synonyms]
    assert len(metric_synonyms) == len(set(metric_synonyms))
    assert len(dimension_synonyms) == len(set(dimension_synonyms))
    assert len(value_synonyms) == len(set(value_synonyms))


def test_invoice_metrics_do_not_touch_card_tables():
    catalog = get_catalog()
    for metric in catalog.metrics.values():
        if metric.fact != "invoices":
            continue
        for token in ("t.", "cd.", "m."):
            assert token not in metric.expression


def test_every_example_is_nonempty():
    for example in get_catalog().examples:
        assert example.area
        assert example.question
