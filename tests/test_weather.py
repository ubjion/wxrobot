from app.services.weather import OpenMeteoWeatherClient, WeatherReport


def test_weather_client_resolves_city_and_reads_current_weather():
    calls = []

    def fake_get(url, params):
        calls.append((url, params))
        if "geocoding" in url:
            return {"results": [{"name": "宁波", "latitude": 29.87, "longitude": 121.55}]}
        return {
            "current": {
                "temperature_2m": 28.5,
                "apparent_temperature": 30.1,
                "relative_humidity_2m": 75,
                "weather_code": 1,
                "wind_speed_10m": 12.4,
            },
            "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
        }

    client = OpenMeteoWeatherClient(http_get=fake_get)

    report = client.get_current("宁波")

    assert report == WeatherReport("宁波", 28.5, 30.1, 75, 1, 12.4)
    assert calls[0][1]["name"] == "宁波"
    assert calls[1][1]["latitude"] == 29.87


def test_weather_client_raises_when_city_is_not_found():
    client = OpenMeteoWeatherClient(http_get=lambda url, params: {})

    try:
        client.get_current("不存在的城市")
    except RuntimeError as exc:
        assert "未找到城市" in str(exc)
    else:
        raise AssertionError("expected city lookup failure")


def test_weather_client_retries_transient_network_failure():
    attempts = []

    def flaky_get(url, params):
        attempts.append(url)
        if len(attempts) == 1:
            raise TimeoutError("temporary timeout")
        if "geocoding" in url:
            return {"results": [{"name": "宁波", "latitude": 29.87, "longitude": 121.55}]}
        return {
            "current": {
                "temperature_2m": 28,
                "apparent_temperature": 30,
                "relative_humidity_2m": 70,
                "weather_code": 0,
                "wind_speed_10m": 10,
            }
        }

    report = OpenMeteoWeatherClient(http_get=flaky_get).get_current("宁波")

    assert report.city == "宁波"
    assert len(attempts) == 3


def test_weather_reuses_injected_http_client_and_closes_it():
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self):
            self.calls = []
            self.closed = 0

        def get(self, url, params, headers, timeout):
            self.calls.append(url)
            if "geocoding" in url:
                return Response({
                    "results": [{"name": "宁波", "latitude": 1, "longitude": 2}]
                })
            return Response({
                "current": {
                    "temperature_2m": 1,
                    "apparent_temperature": 2,
                    "relative_humidity_2m": 3,
                    "weather_code": 0,
                    "wind_speed_10m": 4,
                }
            })

        def close(self):
            self.closed += 1

    raw = Client()
    client = OpenMeteoWeatherClient(http_client=raw)

    client.get_current("宁波")
    client.close()

    assert len(raw.calls) == 2
    assert raw.closed == 1
