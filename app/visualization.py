import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


class EarthquakeVisualizer:
    """Generate visualizations for earthquake data aggregated by category."""

    def __init__(self, output_dir: str = "visualizations") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def generate_bar_chart(
        self,
        data: dict[str, int],
        title: str = "Earthquake Count by County",
        category_label: str = "County",
    ) -> str:
        """Generate a bar chart of earthquake counts by category."""
        df = pd.DataFrame(
            list(data.items()), columns=[category_label, "Count"]
        ).sort_values("Count", ascending=False)

        fig, ax = plt.subplots(figsize=(12, 6))
        ax.bar(df[category_label], df["Count"], color="steelblue")
        ax.set_xlabel(category_label, fontsize=12, fontweight="bold")
        ax.set_ylabel("Number of Earthquakes", fontsize=12, fontweight="bold")
        ax.set_title(title, fontsize=14, fontweight="bold")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        output_path = self.output_dir / "earthquakes_bar_chart.png"
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        return str(output_path)

    def generate_pie_chart(
        self,
        data: dict[str, int],
        title: str = "Earthquake Distribution by County",
        category_label: str = "County",
    ) -> str:
        """Generate a pie chart of earthquake counts by category."""
        df = pd.DataFrame(
            list(data.items()), columns=[category_label, "Count"]
        ).sort_values("Count", ascending=False)

        fig, ax = plt.subplots(figsize=(10, 8))
        ax.pie(
            df["Count"],
            labels=df[category_label],
            autopct="%1.1f%%",
            startangle=90,
            colors=plt.cm.Set3(range(len(df))),
        )
        ax.set_title(title, fontsize=14, fontweight="bold")
        plt.tight_layout()

        output_path = self.output_dir / "earthquakes_pie_chart.png"
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        return str(output_path)

    def generate_trend_chart(
        self, data: dict[str, list[int]], title: str = "Earthquake Trend by County"
    ) -> str:
        """Generate a line chart showing earthquake trends over time/categories by county."""
        fig, ax = plt.subplots(figsize=(12, 6))

        for county, counts in data.items():
            ax.plot(counts, marker="o", label=county, linewidth=2)

        ax.set_xlabel("Period", fontsize=12, fontweight="bold")
        ax.set_ylabel("Number of Earthquakes", fontsize=12, fontweight="bold")
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.legend(loc="best")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        output_path = self.output_dir / "earthquakes_trend_chart.png"
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        return str(output_path)
