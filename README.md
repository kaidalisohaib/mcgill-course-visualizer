# McGill Course Visualizer

## Overview

This project is a full-stack tool for visualizing McGill University's course catalogue, including course dependencies (prerequisites, corequisites), program structures, and more. It consists of a web-based frontend, a backend data processing pipeline, and a web scraping component.

---

## Features
- **Interactive Visualization:** Explore courses, prerequisites, and program structures using an interactive graph (powered by [vis-network](https://visjs.org/)).
- **Search & Filter:** Search by program, course code, or category. Filter and highlight by program or course group.
- **Course Details:** Click on any course to view detailed information, including prerequisites, corequisites, restrictions, and more.
- **Responsive UI:** Modern, responsive design with McGill branding.

---

## Project Structure

- `index.html` — Main web interface
- `js/main.js` — Frontend logic for data loading, graph rendering, and UI interactions
- `css/style.css` — Custom styles and responsive design
- `data/` — Contains processed and raw course/program data in JSON format
- `processing_scripts/` — Python scripts for parsing, cleaning, and enriching course data (including LLM-based prerequisite parsing)
- `mcgill_scraper/` — Scrapy project for extracting program and course data from McGill's course catalogue
- `requirements.txt` — Python dependencies for backend and data processing

---

## How It Works

1. **Scraping:** Use Scrapy spiders (`mcgill_scraper/spiders/`) to extract raw course and program data from McGill's website.
2. **Processing:** Use Python scripts (`processing_scripts/`) to clean, parse, and enrich the data (including LLM-based parsing of prerequisites/corequisites using the Gemini API).
3. **Visualization:** The frontend loads the processed data and provides an interactive interface for exploring programs, courses, and their relationships.

---

## Setup & Usage

### 1. Data Preparation
- Ensure you have Python 3.8+ and [pip](https://pip.pypa.io/en/stable/) installed.
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```
- To scrape new data, run the spiders in `mcgill_scraper/spiders/` using Scrapy.
- To process and enrich data, use the scripts in `processing_scripts/` (see script docstrings for details).
- Place the resulting JSON files in the `data/` directory.

### 2. Frontend
- No build step required. Simply open `index.html` in your browser.
- The app will load data from the `data/` directory and render the interactive course/program graph.

---

## Technologies Used
- **Frontend:** HTML, CSS, JavaScript, [vis-network](https://visjs.org/)
- **Backend/Data Processing:** Python, Scrapy, asyncio, aiohttp, Google Gemini API, dotenv
- **Data:** JSON

---

## Customization
- Adjust styles in `css/style.css`.
- Modify frontend logic in `js/main.js`.
- Update or extend data processing and scraping logic in their respective directories.

---

## Credits
- McGill University course data is publicly available.
- Visualization powered by vis-network.
- Prerequisite parsing powered by Google Gemini API.
