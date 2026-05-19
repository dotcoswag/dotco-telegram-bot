"""
MCP Server for DotCo Swag Lead Scraper
Allows Claude to trigger and manage scraping jobs.

Run: python3 mcp_server.py
"""

import json
import subprocess
import os
import sys
from pathlib import Path
from datetime import datetime

# MCP server implementation
class ScraperMCPServer:
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.results_dir = self.base_dir / "resultados"
        self.results_dir.mkdir(exist_ok=True)

    def list_tools(self):
        """Return available tools for Claude."""
        return [
            {
                "name": "scrape_businesses",
                "description": "Scrape businesses from Google Maps using RapidAPI. Specify cities, categories, and filters.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "market_tier": {
                            "type": "string",
                            "enum": ["tiny_towns", "sweet_spot", "mid_large", "major_metros", "all", "recommended"],
                            "description": "Market size tier (tiny_towns=10-50k, sweet_spot=50-250k, mid_large=250k-1M, major_metros=1M+, recommended=pre-curated)"
                        },
                        "cities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific cities to scrape (e.g., ['Boulder', 'Madison', 'Eugene']). Ignored if market_tier is set."
                        },
                        "states": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "States to include (e.g., ['Colorado', 'Oregon', 'Wisconsin'])"
                        },
                        "categories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Business categories to search (e.g., ['smoke shop', 'cannabis dispensary', 'gym'])"
                        },
                        "min_score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 7,
                            "description": "Minimum lead score (0=all, 7=only hottest). Default: 3"
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Max number of leads to save. Omit for unlimited."
                        },
                        "recommended_tier": {
                            "type": "string",
                            "enum": ["sweet_spot", "tiny_towns"],
                            "description": "Which recommended list tier to use (only if market_tier='recommended')"
                        }
                    },
                    "required": ["market_tier"]
                }
            },
            {
                "name": "list_results",
                "description": "List all recent scraping results (CSV files).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "How many recent results to show (default: 10)"
                        }
                    }
                }
            },
            {
                "name": "get_result_summary",
                "description": "Get summary stats from a CSV result file.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "CSV filename (e.g., 'dotco_leads_20240515_143022.csv')"
                        }
                    },
                    "required": ["filename"]
                }
            },
            {
                "name": "resume_scrape",
                "description": "Resume an interrupted scraping session from a checkpoint.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "csv_filename": {
                            "type": "string",
                            "description": "The CSV filename to resume (must have a .checkpoint.json file)"
                        }
                    },
                    "required": ["csv_filename"]
                }
            }
        ]

    def scrape_businesses(self, market_tier, cities=None, states=None, categories=None,
                         min_score=3, limit=None, recommended_tier=None):
        """Trigger a scraping job with the given parameters."""

        # Create a config JSON for the scraper
        config = {
            "market_tier": market_tier,
            "cities": cities or [],
            "states": states or [],
            "categories": categories or [],
            "min_score": min_score,
            "limit": limit,
            "recommended_tier": recommended_tier,
        }

        # Generate script to run interactively
        script_lines = self._generate_interactive_script(config)

        # Write temporary script
        temp_script = self.base_dir / "temp_scrape.py"
        with open(temp_script, "w") as f:
            f.write("\n".join(script_lines))

        # Run the scraper
        try:
            result = subprocess.run(
                [sys.executable, str(temp_script)],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            # Clean up temp script
            temp_script.unlink()

            if result.returncode == 0:
                return {
                    "status": "success",
                    "message": "Scraping completed successfully",
                    "output": result.stdout,
                    "stderr": result.stderr
                }
            else:
                return {
                    "status": "error",
                    "message": f"Scraping failed with code {result.returncode}",
                    "error": result.stderr,
                    "output": result.stdout
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": "Scraping timed out after 1 hour"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error running scraper: {str(e)}"
            }

    def _generate_interactive_script(self, config):
        """Generate a Python script that automates the scraper with given config."""

        # Build market tier selection
        tier_map = {
            "tiny_towns": "1",
            "sweet_spot": "2",
            "mid_large": "3",
            "major_metros": "4",
            "all": "5",
            "recommended": "6",
        }

        tier_choice = tier_map.get(config["market_tier"], "2")

        # Build categories string
        categories_input = " ".join(config["categories"]) if config["categories"] else ""

        script = [
            "#!/usr/bin/env python3",
            "import sys",
            "import subprocess",
            "",
            "# Auto-scraper script generated by MCP server",
            "# This script runs the scraper with pre-configured options",
            "",
            "# Import the scraper modules",
            "from main import cargar_ciudades, elegir_alcance, elegir_categorias, elegir_limite, elegir_min_score, confirmar, correr_scraping",
            "from main import elegir_rango_poblacion, elegir_mercados_recomendados, filtrar_data_por_poblacion",
            "",
            "print('🤖 Claude MCP Scraper: Auto-Running with provided config')",
            "print()",
            "",
            "# Load cities",
            "data = cargar_ciudades()",
            "",
            "# Step 1: Market tier selection",
            f"tier_choice = '{tier_choice}'",
            "if tier_choice == '6':",
            f"    recommended_tier = '{config.get('recommended_tier', 'sweet_spot')}'",
            "    if recommended_tier == 'tiny_towns':",
            "        localidades = [",
            "            ('Aspen', 'Colorado'), ('Montpelier', 'Vermont'), ('Jackson', 'Wyoming'),",
            "            ('Moab', 'Utah'), ('Park City', 'Utah'), ('Vail', 'Colorado'), ('Telluride', 'Colorado'),",
            "        ]",
            "    else:  # sweet_spot",
            "        localidades = [",
            "            ('Madison', 'Wisconsin'), ('Boulder', 'Colorado'), ('Fort Collins', 'Colorado'),",
            "            ('Eugene', 'Oregon'), ('Bend', 'Oregon'), ('Asheville', 'North Carolina'),",
            "            ('Chapel Hill', 'North Carolina'), ('Santa Fe', 'New Mexico'), ('Burlington', 'Vermont'),",
            "            ('Ithaca', 'New York'), ('Bozeman', 'Montana'), ('Flagstaff', 'Arizona'), ('Sedona', 'Arizona'),",
            "        ]",
            "else:",
            "    min_pop, max_pop, _ = elegir_rango_poblacion()",
            "    data_filtrada = filtrar_data_por_poblacion(data, min_pop, max_pop)",
            "    localidades = elegir_alcance(data_filtrada)",
            "",
            "# Step 2: Categories",
        ]

        if config["categories"]:
            script.append(f"categories = {config['categories']}")
        else:
            script.append("categories = elegir_categorias()")

        script.extend([
            "",
            "# Step 3: Limit",
            f"limite = {config.get('limit', 'None')}",
            "",
            "# Step 4: Min score",
            f"min_score = {config.get('min_score', 3)}",
            "",
            "# Step 5: Scrape",
            "print('Starting scrape...')",
            "correr_scraping(localidades, categories, limite, min_score)",
            "",
            "print('✅ Scraping complete!')",
        ])

        return script

    def list_results(self, limit=10):
        """List recent result files."""
        if not self.results_dir.exists():
            return {"status": "error", "message": "No results directory found"}

        csv_files = sorted(
            self.results_dir.glob("dotco_leads_*.csv"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )[:limit]

        results = []
        for csv_file in csv_files:
            checkpoint_file = csv_file.parent / (csv_file.stem + ".checkpoint.json")
            results.append({
                "filename": csv_file.name,
                "created": datetime.fromtimestamp(csv_file.stat().st_mtime).isoformat(),
                "size_bytes": csv_file.stat().st_size,
                "has_checkpoint": checkpoint_file.exists(),
            })

        return {
            "status": "success",
            "results": results,
            "total": len(results)
        }

    def get_result_summary(self, filename):
        """Get summary stats from a CSV file."""
        csv_path = self.results_dir / filename

        if not csv_path.exists():
            return {"status": "error", "message": f"File not found: {filename}"}

        try:
            import csv

            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                return {"status": "error", "message": "CSV is empty"}

            # Calculate stats
            lead_scores = []
            verified_count = 0
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
                    verified_count += 1
                if row.get("email"):
                    with_email += 1
                if row.get("telefono"):
                    with_phone += 1
                if row.get("website"):
                    with_website += 1

            avg_score = sum(lead_scores) / len(lead_scores) if lead_scores else 0

            return {
                "status": "success",
                "filename": filename,
                "total_leads": len(rows),
                "avg_lead_score": round(avg_score, 2),
                "verified_count": verified_count,
                "with_email": with_email,
                "with_phone": with_phone,
                "with_website": with_website,
                "top_categories": self._get_top_categories(rows, 5),
                "top_cities": self._get_top_cities(rows, 5),
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error reading file: {str(e)}"
            }

    def _get_top_categories(self, rows, limit):
        """Get most common business categories."""
        from collections import Counter
        categories = [row.get("categoria_buscada", "Unknown") for row in rows]
        return dict(Counter(categories).most_common(limit))

    def _get_top_cities(self, rows, limit):
        """Get most common cities."""
        from collections import Counter
        cities = [f"{row.get('city', 'Unknown')}, {row.get('state', '')}" for row in rows]
        return dict(Counter(cities).most_common(limit))

    def resume_scrape(self, csv_filename):
        """Resume scraping from a checkpoint."""
        csv_path = self.results_dir / csv_filename
        checkpoint_path = self.results_dir / (Path(csv_filename).stem + ".checkpoint.json")

        if not csv_path.exists():
            return {"status": "error", "message": f"CSV file not found: {csv_filename}"}

        if not checkpoint_path.exists():
            return {"status": "error", "message": f"Checkpoint file not found for {csv_filename}"}

        # Generate resume script
        script_lines = [
            "#!/usr/bin/env python3",
            "from main import correr_scraping, cargar_ciudades, elegir_categorias",
            "",
            "print('🤖 Resuming scrape from checkpoint...')",
            "data = cargar_ciudades()",
            "categories = elegir_categorias()",
            "correr_scraping(None, categories, None, 0)",  # Will auto-detect from checkpoint
        ]

        temp_script = self.base_dir / "temp_resume.py"
        with open(temp_script, "w") as f:
            f.write("\n".join(script_lines))

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
                "output": result.stdout,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error resuming: {str(e)}"
            }

    def handle_request(self, request):
        """Handle MCP requests from Claude."""
        if request.get("method") == "tools/list":
            return {"tools": self.list_tools()}

        elif request.get("method") == "tool/call":
            tool_name = request.get("params", {}).get("name")
            tool_input = request.get("params", {}).get("arguments", {})

            if tool_name == "scrape_businesses":
                return self.scrape_businesses(**tool_input)
            elif tool_name == "list_results":
                return self.list_results(**tool_input)
            elif tool_name == "get_result_summary":
                return self.get_result_summary(**tool_input)
            elif tool_name == "resume_scrape":
                return self.resume_scrape(**tool_input)
            else:
                return {"status": "error", "message": f"Unknown tool: {tool_name}"}

        return {"status": "error", "message": "Unknown request"}


# Main entry point for MCP server
if __name__ == "__main__":
    import json

    server = ScraperMCPServer()

    print("🚀 DotCo Scraper MCP Server started", file=sys.stderr)
    print("Waiting for Claude requests...", file=sys.stderr)

    # Read requests from stdin
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = server.handle_request(request)
            print(json.dumps(response))
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON"}))
        except Exception as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
