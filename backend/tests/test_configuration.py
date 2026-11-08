import unittest

from app.main import parse_cors_origins


class CorsConfigurationTests(unittest.TestCase):
    def test_accepts_local_lan_and_deployed_origins(self) -> None:
        origins = parse_cors_origins(
            "http://localhost:5173, http://192.168.1.20:5173/, "
            "https://hangout.example.com"
        )

        self.assertEqual(
            origins,
            [
                "http://localhost:5173",
                "http://192.168.1.20:5173",
                "https://hangout.example.com",
            ],
        )

    def test_deduplicates_origins(self) -> None:
        origins = parse_cors_origins(
            "http://localhost:5173,http://localhost:5173/"
        )

        self.assertEqual(origins, ["http://localhost:5173"])

    def test_rejects_wildcard_with_credentials(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "cannot contain '\\*'"):
            parse_cors_origins("*")

    def test_rejects_non_origin_urls(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Invalid CORS origin"):
            parse_cors_origins("https://hangout.example.com/app")


if __name__ == "__main__":
    unittest.main()
