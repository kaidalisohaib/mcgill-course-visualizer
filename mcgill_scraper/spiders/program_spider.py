import scrapy
import re
import json
from urllib.parse import unquote


class ProgramSpider(scrapy.Spider):
    name = "mcgill_programs"
    allowed_domains = ["coursecatalogue.mcgill.ca"]
    start_urls = ["https://coursecatalogue.mcgill.ca/en/undergraduate/"]

    def __init__(self, *args, **kwargs):
        super(ProgramSpider, self).__init__(*args, **kwargs)
        self.crawled_urls = set()

    def start_requests(self):
        # yield scrapy.Request(self.start_urls[0], callback=self.parse_faculty_page, errback=self.errback_httpbin)
        
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse, errback=self.errback_httpbin)

    def errback_httpbin(self, failure):
        self.logger.error(f"Request failed: {failure.request.url}")

    def extract_faculty_name(self, url):
        # Extract faculty name from URL, e.g., /undergraduate/arts/ -> Arts
        match = re.search(r"/undergraduate/([^/]+)/?", url)
        if match:
            faculty = match.group(1).replace("-", " ").title()
            return faculty
        return None

    def extract_unit_name(self, url):
        # Extract unit name from URL, e.g., /programs/biology/ -> Biology
        match = re.search(r"/programs/([^/]+)/?", url)
        if match:
            unit = match.group(1).replace("-", " ").title()
            return unit
        return None

    def parse(self, response):
        self.logger.info(f"Starting crawl from {response.url}")
        self.crawled_urls.add(response.url)

        faculty_links = response.css("div.sitemap a")
        for link in faculty_links:
            url = link.css("::attr(href)").get()
            if url and url.startswith("/"):
                full_url = response.urljoin(url)
                if full_url not in self.crawled_urls:
                    self.crawled_urls.add(full_url)
                    faculty_name = link.css("::text").get().strip()
                    yield response.follow(
                        url,
                        callback=self.parse_faculty_page,
                        meta={"faculty": faculty_name},
                    )

    def parse_faculty_page(self, response):
        self.log(f"Parsing faculty page: {response.url}")

        # Check for Programs tab in nav bar
        programs_tab = response.xpath(
            "//ul[contains(@class, 'clearfix')]//a[contains(text(), 'Programs')]"
        )
        if programs_tab:
            # Check if there's a nested structure (sitemap > ul > li > ul)
            has_nested_structure = bool(response.css("div.sitemap > ul > li > ul"))

            if has_nested_structure:
                # This is actually showing programs within units
                # Get the top level items (units)
                top_level_items = response.css("div.sitemap > ul > li")
                for unit_item in top_level_items:
                    # Get unit info
                    unit_links = unit_item.css("a")
                    if not unit_links:
                        continue
                    
                    unit_link = unit_links[0] if unit_links else None  # Get first selector
                    if not unit_link:
                        continue

                    unit_name = unit_link.css("::text").get().strip()

                    # Get all programs within this unit
                    program_links = unit_item.css("ul li a")
                    for program in program_links:
                        url = program.css("::attr(href)").get()
                        if url and url.startswith("/"):
                            full_url = response.urljoin(url)
                            if full_url not in self.crawled_urls:
                                self.crawled_urls.add(full_url)
                                program_name = program.css("::text").get().strip()
                                yield response.follow(
                                    url,
                                    callback=self.parse_program_courses,
                                    meta={
                                        "faculty": response.meta.get("faculty"),
                                        "unit": unit_name,
                                        "program_name": program_name,
                                    },
                                )
            else:
                # Regular programs page without units
                program_links = response.css("div.sitemap a")
                for program in program_links:
                    url = program.css("::attr(href)").get()
                    if url and url.startswith("/"):
                        full_url = response.urljoin(url)
                        if full_url not in self.crawled_urls:
                            self.crawled_urls.add(full_url)
                            program_name = program.css("::text").get().strip()
                            yield response.follow(
                                url,
                                callback=self.parse_program_courses,
                                meta={
                                    "faculty": response.meta.get("faculty"),
                                    "program_name": program_name,
                                },
                            )
            return

        # If no Programs tab, check for Academic Units tab
        units_tab = response.xpath(
            "//ul[contains(@class, 'clearfix')]//a[contains(text(), 'Academic Units')]"
        )
        if units_tab:
            unit_links = response.css("div.sitemap a")
            for link in unit_links:
                url = link.css("::attr(href)").get()
                if url and url.startswith("/"):
                    full_url = response.urljoin(url)
                    if full_url not in self.crawled_urls:
                        self.crawled_urls.add(full_url)
                        unit_name = link.css("::text").get().strip()
                        yield response.follow(
                            url,
                            callback=self.parse_unit_page,
                            meta={
                                "faculty": response.meta.get("faculty"),
                                "unit": unit_name,
                            },
                        )
            return

        # If neither tab is found, try to find any program links in the content
        content_links = response.css("div.sitemap a")
        for link in content_links:
            url = link.css("::attr(href)").get()
            if (
                url
                and url.startswith("/")
                and ("/programs/" in url or "/major/" in url or "/minor/" in url)
            ):
                full_url = response.urljoin(url)
                if full_url not in self.crawled_urls:
                    self.crawled_urls.add(full_url)
                    program_name = link.css("::text").get().strip()
                    yield response.follow(
                        url,
                        callback=self.parse_program_courses,
                        meta={
                            "faculty": response.meta.get("faculty"),
                            "program_name": program_name,
                        },
                    )

        self.logger.debug(f"No program or unit links found in faculty: { response.meta.get('faculty')}")

    def parse_unit_page(self, response):
        faculty = response.meta.get("faculty")
        unit = response.meta.get("unit", self.extract_unit_name(response.url))
        self.logger.info(f"Parsing unit page: {faculty} > {unit} - {response.url}")

        # program_sections = response.xpath(
        #     "//h2[contains(@class, 'book-heading') and contains(text(), 'Available Programs')]/following-sibling::div[@class='sitemap'][1]"
        # )
        # if program_sections:
        #     for section in program_sections:
        #         program_links = section.css("a")
        #         for link in program_links:
        #             url = link.css("::attr(href)").get()
        #             if url and url.startswith("/"):
        #                 full_url = response.urljoin(url)
        #                 if full_url not in self.crawled_urls:
        #                     self.crawled_urls.add(full_url)
        #                     program_name = link.css("::text").get().strip()
        #                     yield response.follow(
        #                         url,
        #                         callback=self.parse_program_courses,
        #                         meta={
        #                             "faculty": faculty,
        #                             "unit": unit,
        #                             "program_name": program_name,
        #                         },
        #                     )
        #     return

        # Fallback: try to find any /programs/ links
        program_links = response.css("div.sitemap a")
        for link in program_links:
            url = link.css("::attr(href)").get()
            # if url and "/programs/" in url:
            full_url = response.urljoin(url)
            print(url)
            if full_url not in self.crawled_urls:
                self.crawled_urls.add(full_url)
                program_name = link.css("::text").get().strip()
                yield response.follow(
                    url,
                    callback=self.parse_program_courses,
                    meta={
                        "faculty": faculty,
                        "unit": unit,
                        "program_name": program_name,
                    },
                )

    def parse_program_courses(self, response):
        faculty = response.meta.get("faculty")
        unit = response.meta.get("unit")
        program_name = response.meta.get("program_name")

        if not program_name:
            program_name = response.css("h1.page-title::text").get()
            if not program_name:
                self.logger.warning(f"No program name found for URL: {response.url}")
                return
            program_name = program_name.strip()

        # Extract all course codes from tables
        course_codes = []
        # Get all rows from all course tables, excluding header rows
        for course_row in response.css("table.sc_courselist tr"):
            # Skip header rows
            if 'colspan' in course_row.get():
                continue
            course_code = course_row.css("td.codecol::text").get()
            if course_code:
                # Replace space with hyphen in course code
                formatted_code = course_code.strip().replace(" ", "-")
                course_codes.append(formatted_code)

        self.logger.info(
            f"Found program: {faculty} > {unit} > {program_name} with {len(course_codes)} courses"
        )
        
        yield {
            "faculty": faculty,
            "unit": unit,
            "program": program_name,
            "url": response.url,
            "courses": course_codes
        }
