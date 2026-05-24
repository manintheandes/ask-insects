import tempfile
import unittest
from pathlib import Path

from askinsects.sources.paho_surveillance import fetch_paho_dengue_surveillance_records


REPORT_HTML = """
<html>
<body>
<center><h3 class="arrow">Actualizado: Jan 16 2026 12:47AM</h3></center>
<h2>Situación epidemiológica del dengue en las Américas</h2>
A la semana epidemiológica 50, 2024 </br>
<h2>Indicadores de la semana 50, 2024</h2>
<ul>
<li>62,707 casos sospechosos</li>
<li>23,034 casos confirmados (36.7%)</li>
<li>219 dengue grave</li>
<li>125 muertes</li>
<li>0.199% letalidad</li>
<li>32 países con datos reportados</li>
</ul>
<h2>Indicadores de las semanas 1 - 50, 2024</h2>
<ul>
<li>12,970,602 casos sospechosos</li>
<li>6,963,431 casos confirmados (53.7%)</li>
<li>22,842 casos de dengue grave</li>
<li>8,340 muertes</li>
<li>0.064% letalidad</li>
<li>49 países con datos reportados</li>
</ul>
<p>Entre las semanas epidemiológicas (SE) 1 y 50 del 2024, se reportaron un total de 12,970,602 casos sospechosos de dengue (incidencia acumulada de 1,286.22 casos por 100,000 hab. Esta cifra representa un incremento de 190% en comparación al mismo periodo del 2023 y 366% con respecto al promedio de los últimos 5 años.</p>
<p><b>Gráfico 1.</b> Número total de casos sospechosos de dengue a la SE 50 en 2024.</p>
<img src="https://ais.paho.org/ArboPortal/img/2024/ComparativoDENGAME.png">
<h2>Análisis por subregión</h2>
<p><b>Subregión Centroamérica y México.</b> Un total de 11,946 nuevos casos sospechosos de dengue fueron registrados en la SE 50. Ningún país muestra un incremento de casos en comparación al promedio de sus cuatro semanas epidemiológicas previas (Gráficos 3 y 4).</p>
<p><b>Subregión Cono Sur.</b> Se notifican 43,864 nuevos casos sospechosos de dengue en la SE 50. Argentina , Brasil , Paraguay , Uruguay muestra un incremento de casos en comparación al promedio de sus cuatro semanas epidemiológicas previas (Gráficos 3 y 7).</p>
<p>Los cuatro serotipos del virus dengue (DENV1-DENV-2, DENV-3, and DENV-4) han sido identificados en la Región de las Américas durante 2024. En 10 países de la Región ( Brasil , Colombia , Costa Rica , El Salvador ) se reporta la circulación simultánea de los cuatros serotipos del DENV. (Ver gráfico 8).</p>
</body>
</html>
"""


DASHBOARD_HTML = """
<html><body>
<iframe src="https://phip.paho.org/trusted/example/views/1001en/Numeralia"></iframe>
</body></html>
"""


class PahoSurveillanceSourceTests(unittest.TestCase):
    def test_fetch_paho_dengue_surveillance_records_parses_report_and_dashboard_gaps(self):
        def fake_fetch(url):
            if "dashboard" in url:
                return DASHBOARD_HTML
            return REPORT_HTML

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_paho_dengue_surveillance_records(
                [{"url": "https://example.org/report", "landing_url": "https://example.org/landing"}],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=fake_fetch,
                retrieved_at="2026-05-24T00:00:00Z",
                dashboard_pages=["https://example.org/dashboard"],
            )

            self.assertEqual(result.source_id, "aedes_paho_dengue_surveillance")
            self.assertGreaterEqual(len(result.records), 6)
            self.assertEqual(result.report_count, 1)
            self.assertEqual(result.dashboard_page_count, 1)
            weekly = next(record for record in result.records if record.payload["aggregation_type"] == "regional_week_summary")
            self.assertEqual(weekly.lane, "public_health")
            self.assertEqual(weekly.species, "Aedes aegypti")
            self.assertEqual(weekly.payload["metrics"]["suspected_cases"], 62707)
            self.assertEqual(weekly.payload["metrics"]["deaths"], 125)
            cumulative = next(record for record in result.records if record.payload["aggregation_type"] == "regional_year_to_date_summary")
            self.assertEqual(cumulative.payload["metrics"]["cumulative_incidence_per_100k"], 1286.22)
            subregion = next(record for record in result.records if record.payload["aggregation_type"] == "subregion_week_summary" and record.payload["subregion"] == "Cono Sur")
            self.assertIn("Brasil", subregion.payload["countries_with_increase"])
            self.assertEqual(
                sum(1 for record in result.records if record.payload["aggregation_type"] == "subregion_week_summary"),
                2,
            )
            serotypes = next(record for record in result.records if record.payload["aggregation_type"] == "serotype_regional_summary")
            self.assertIn("DENV-4", serotypes.payload["serotypes"])
            self.assertEqual(
                serotypes.payload["countries_with_all_four_serotypes"],
                ["Brasil", "Colombia", "Costa Rica", "El Salvador"],
            )
            visual = next(record for record in result.records if record.payload["aggregation_type"] == "surveillance_visual")
            self.assertEqual(visual.media_url, "https://ais.paho.org/ArboPortal/img/2024/ComparativoDENGAME.png")
            self.assertEqual(result.gaps[0]["reason"], "paho_dashboard_data_not_yet_cell_queryable")
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

    def test_fetch_paho_dengue_surveillance_records_records_fetch_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_paho_dengue_surveillance_records(
                [{"url": "https://example.org/report"}],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T00:00:00Z",
                dashboard_pages=(),
            )

            self.assertFalse(result.records)
            self.assertEqual(result.gaps[0]["reason"], "paho_dengue_report_fetch_failed")

    def test_fetch_paho_dengue_surveillance_records_does_not_index_unparseable_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_paho_dengue_surveillance_records(
                [{"url": "https://example.org/report"}],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: "<html>not a PAHO report</html>",
                retrieved_at="2026-05-24T00:00:00Z",
                dashboard_pages=(),
            )

            self.assertFalse(result.records)
            self.assertEqual(result.gaps[0]["reason"], "paho_dengue_report_no_records_parsed")


if __name__ == "__main__":
    unittest.main()
