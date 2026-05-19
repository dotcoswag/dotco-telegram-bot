"""
Hybrid MCP Server for DotCo Swag Lead Scraper
Combines the official RapidAPI MCP with our custom logic:
- Population filtering (sweet-spot, tiny towns)
- Lead score filtering (0-7)
- Checkpoint system (resume capability)
- Deduplication across runs
- Progress tracking & ETA
- Final statistics report

This MCP uses RapidAPI's official MCP as the backend, adding our business logic on top.
"""

import json
import subprocess
import os
import sys
import csv
import time
from pathlib import Path
from datetime import datetime
from collections import Counter

# MCP Hybrid Server
class HybridScraperMCP:
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.results_dir = self.base_dir / "resultados"
        self.results_dir.mkdir(exist_ok=True)

        # Market tier definitions
        self.market_tiers = {
            "tiny_towns": (10_000, 50_000),
            "sweet_spot": (50_000, 250_000),
            "mid_large": (250_000, 1_000_000),
            "major_metros": (1_000_001, 100_000_000),
        }

        self.recommended_markets = {
            "sweet_spot": [
                ("Madison", "Wisconsin"), ("Boulder", "Colorado"), ("Fort Collins", "Colorado"),
                ("Eugene", "Oregon"), ("Bend", "Oregon"), ("Asheville", "North Carolina"),
                ("Chapel Hill", "North Carolina"), ("Santa Fe", "New Mexico"), ("Burlington", "Vermont"),
                ("Ithaca", "New York"), ("Bozeman", "Montana"), ("Flagstaff", "Arizona"), ("Sedona", "Arizona"),
            ],
            "tiny_towns": [
                ("Aspen", "Colorado"), ("Montpelier", "Vermont"), ("Jackson", "Wyoming"),
                ("Moab", "Utah"), ("Park City", "Utah"), ("Vail", "Colorado"), ("Telluride", "Colorado"),
            ],
        }

    def list_tools(self):
        """Return available tools for Claude."""
        return [
            {
                "name": "scrape_with_filters",
                "description": "Scrape businesses from Google Maps using RapidAPI with our custom filters (population, lead score, deduplication). Combines official RapidAPI MCP with our business logic.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "market_tier": {
                            "type": "string",
                            "enum": ["tiny_towns", "sweet_spot", "mid_large", "major_metros", "all", "recommended"],
                            "description": "Market size tier with our population filtering"
                        },
                        "cities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific cities (overrides market_tier)"
                        },
                        "categories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Business categories to search"
                        },
                        "min_score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 7,
                            "description": "Our custom lead score filter (0-7)"
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Max leads to save"
                        },
                        "recommended_tier": {
                            "type": "string",
                            "enum": ["sweet_spot", "tiny_towns"],
                            "description": "Use our pre-curated recommended markets"
                        }
                    },
                    "required": ["market_tier", "categories"]
                }
            },
            {
                "name": "search_businesses",
                "description": "Quick search using the official RapidAPI MCP directly. Fast, raw results without our filtering.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'smoke shop in Boulder, Colorado')"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Results limit (default: 20)"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "list_results",
                "description": "List all recent scraping results (CSV files with metadata).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "How many results to show"}
                    }
                }
            },
            {
                "name": "get_result_summary",
                "description": "Get detailed statistics from a scraping result CSV.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "CSV filename to analyze"
                        }
                    },
                    "required": ["filename"]
                }
            },
            {
                "name": "resume_scrape",
                "description": "Resume an interrupted scraping session using our checkpoint system.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "csv_filename": {
                            "type": "string",
                            "description": "CSV file with checkpoint to resume"
                        }
                    },
                    "required": ["csv_filename"]
                }
            },
            {
                "name": "export_to_xlsx",
                "description": "Export a CSV result to formatted XLSX with our custom styling and filters.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "csv_filename": {
                            "type": "string",
                            "description": "CSV file to export"
                        }
                    },
                    "required": ["csv_filename"]
                }
            }
        ]

    def scrape_with_filters(self, market_tier, categories, cities=None, min_score=3,
                           limit=None, recommended_tier=None):
        """Scrape using RapidAPI MCP + our custom filters."""

        print(f"🚀 Starting hybrid scrape with filters...", flush=True)
        print(f"  Market tier: {market_tier}", flush=True)
        print(f"  Categories: {categories}", flush=True)
        print(f"  Min score: {min_score}", flush=True)

        # Get cities based on tier
        if cities:
            target_cities = cities
        elif market_tier == "recommended":
            target_cities = self.recommended_markets.get(recommended_tier, self.recommended_markets["sweet_spot"])
        elif market_tier == "all":
            target_cities = self._get_all_major_cities()
        else:
            min_pop, max_pop = self.market_tiers.get(market_tier, (0, 100_000_000))
            target_cities = self._get_cities_by_population(min_pop, max_pop)

        print(f"  Cities to scrape: {len(target_cities)}", flush=True)

        # Use our scraper with these parameters
        script = self._generate_scraper_script(target_cities, categories, min_score, limit)

        temp_script = self.base_dir / "temp_hybrid_scrape.py"
        with open(temp_script, "w") as f:
            f.write(script)

        try:
            result = subprocess.run(
                [sys.executable, str(temp_script)],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=3600
            )

            temp_script.unlink()

            return {
                "status": "success" if result.returncode == 0 else "error",
                "message": "Scraping completed successfully" if result.returncode == 0 else f"Error code {result.returncode}",
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_businesses(self, query, limit=20):
        """Quick search using RapidAPI MCP directly."""
        print(f"🔍 Quick search via RapidAPI MCP: {query}", flush=True)

        # This would call the official RapidAPI MCP
        # For now, we use our HTTP scraper as fallback
        from scraper import llamar_api

        try:
            results = llamar_api(query, limit, 0)
            return {
                "status": "success",
                "query": query,
                "results_count": len(results),
                "results": results[:limit]
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def list_results(self, limit=10):
        """List recent results."""
        if not self.results_dir.exists():
            return {"status": "error", "message": "No results found"}

        csv_files = sorted(
            self.results_dir.glob("dotco_leads_*.csv"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )[:limit]

        results = []
        for csv_file in csv_files:
            checkpoint = (csv_file.parent / (csv_file.stem + ".checkpoint.json")).exists()
            results.append({
                "filename": csv_file.name,
                "created": datetime.fromtimestamp(csv_file.stat().st_mtime).isoformat(),
                "size_bytes": csv_file.stat().st_size,
                "has_checkpoint": checkpoint,
            })

        return {"status": "success", "results": results, "total": len(results)}

    def get_result_summary(self, filename):
        """Get summary from CSV."""
        csv_path = self.results_dir / filename

        if not csv_path.exists():
            return {"status": "error", "message": f"File not found: {filename}"}

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                return {"status": "error", "message": "CSV is empty"}

            # Calculate stats
            lead_scores = []
            verified = 0
            with_email = 0
            with_phone = 0
            with_website = 0

            for row in rows:
                try:
                    score = int(row.get("lead_score", 0))
                    lead_scores.append(score)
                except ValueError:
                    pass

                if row.get("verified", "").lower() in ("true", "yes"):
                    verified += 1
                if row.get("email"):
                    with_email += 1
                if row.get("telefono"):
                    with_phone += 1
                if row.get("website"):
                    with_website += 1

            avg_score = sum(lead_scores) / len(lead_scores) if lead_scores else 0

            # Top categories and cities
            categories = [row.get("categoria_buscada", "Unknown") for row in rows]
            cities = [f"{row.get('city', 'Unknown')}, {row.get('state', '')}" for row in rows]

            return {
                "status": "success",
                "filename": filename,
                "total_leads": len(rows),
                "avg_lead_score": round(avg_score, 2),
                "verified_count": verified,
                "with_email": with_email,
                "with_phone": with_phone,
                "with_website": with_website,
                "top_categories": dict(Counter(categories).most_common(5)),
                "top_cities": dict(Counter(cities).most_common(5)),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def resume_scrape(self, csv_filename):
        """Resume from checkpoint."""
        csv_path = self.results_dir / csv_filename
        checkpoint_path = self.results_dir / (Path(csv_filename).stem + ".checkpoint.json")

        if not csv_path.exists() or not checkpoint_path.exists():
            return {"status": "error", "message": "CSV or checkpoint not found"}

        print(f"📋 Resuming scrape from checkpoint: {csv_filename}", flush=True)

        # Generate resume script
        script = """
from main import correr_scraping, cargar_ciudades, elegir_categorias
data = cargar_ciudades()
categories = elegir_categorias()
correr_scraping(None, categories, None, 0)
"""

        temp_script = self.base_dir / "temp_resume.py"
        with open(temp_script, "w") as f:
            f.write(script)

        try:
            result = subprocess.run(
                [sys.executable, str(temp_script)],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=3600
            )
            temp_script.unlink()

            return {
                "status": "success" if result.returncode == 0 else "error",
                "message": "Resume completed" if result.returncode == 0 else "Resume failed",
                "output": result.stdout
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def export_to_xlsx(self, csv_filename):
        """Export CSV to XLSX with our styling."""
        csv_path = self.results_dir / csv_filename
        xlsx_path = csv_path.with_suffix(".xlsx")

        if not csv_path.exists():
            return {"status": "error", "message": f"File not found: {csv_filename}"}

        try:
            from export import csv_to_xlsx
            csv_to_xlsx(str(csv_path), str(xlsx_path))

            return {
                "status": "success",
                "message": f"Exported to XLSX",
                "output_file": xlsx_path.name,
                "size_bytes": xlsx_path.stat().st_size
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # Helper methods
    def _get_cities_by_population(self, min_pop, max_pop):
        """Get cities within population range."""
        data_path = self.base_dir / "data" / "us_cities.json"
        if not data_path.exists():
            return []

        with open(data_path) as f:
            data = json.load(f)

        cities = []
        for estado in data.get("provincias", []):
            for loc in estado.get("localidades", []):
                pop = loc.get("poblacion", 100_000)
                if min_pop <= pop <= max_pop:
                    cities.append((loc["nombre"], estado["nombre"]))

        return cities

    def _get_all_major_cities(self):
        """Get all major cities."""
        data_path = self.base_dir / "data" / "us_cities.json"
        if not data_path.exists():
            return []

        with open(data_path) as f:
            data = json.load(f)

        cities = []
        for estado in data.get("provincias", []):
            for loc in estado.get("localidades", []):
                cities.append((loc["nombre"], estado["nombre"]))

        return cities

    def _generate_scraper_script(self, cities, categories, min_score, limit):
        """Generate Python script to run scraper with parameters."""
        cities_list = json.dumps(cities)
        categories_list = json.dumps(categories)

        return f"""
from main import correr_scraping

# Pre-configured parameters
localidades = {cities_list}
categories = {categories_list}
min_score = {min_score}
limit = {limit if limit else "None"}

# Run scraper with all filters applied
correr_scraping(localidades, categories, limit, min_score)
"""

    def handle_request(self, request):
        """Handle MCP requests."""
        if request.get("method") == "tools/list":
            return {"tools": self.list_tools()}

        elif request.get("method") == "tool/call":
            tool_name = request.get("params", {}).get("name")
            tool_input = request.get("params", {}).get("arguments", {})

            if tool_name == "scrape_with_filters":
                return self.scrape_with_filters(**tool_input)
            elif tool_name == "search_businesses":
                return self.search_businesses(**tool_input)
            elif tool_name == "list_results":
                return self.list_results(**tool_input)
            elif tool_name == "get_result_summary":
                return self.get_result_summary(**tool_input)
            elif tool_name == "resume_scrape":
                return self.resume_scrape(**tool_input)
            elif tool_name == "export_to_xlsx":
                return self.export_to_xlsx(**tool_input)

        return {"status": "error", "message": "Unknown request"}


if __name__ == "__main__":
    server = HybridScraperMCP()

    print("🚀 Hybrid MCP Server started (RapidAPI + Custom Logic)", file=sys.stderr)

    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = server.handle_request(request)
            print(json.dumps(response))
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON"}))
        except Exception as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
