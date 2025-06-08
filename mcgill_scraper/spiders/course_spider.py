import scrapy
import re


class CourseSpider(scrapy.Spider):
    name = "mcgill_course_info"
    allowed_domains = ["coursecatalogue.mcgill.ca"]
    start_urls = ["https://coursecatalogue.mcgill.ca/courses/"]

    def parse(self, response):
        """
        This method is called to handle the response downloaded for each of the
        requests generated from start_urls. It extracts links to individual
        course pages and follows them.
        """
        self.log(f"Visited main course listing: {response.url}")

        course_links = response.css(
            "div#textcontainer.page_content ul li a::attr(href)"
        ).getall()
        self.log(f"Found {len(course_links)} direct course links on the main page.")

        for link in course_links:
            if link:
                course_page_url = response.urljoin(link)
                yield response.follow(course_page_url, callback=self.parse_course_page)

    def parse_course_page(self, response):
        """
        This method is called to handle the response downloaded for each
        individual course page. It extracts detailed information about the course.
        """
        # --- COURSE CODE AND TITLE EXTRACTION ---
        course_code_from_url = self.get_course_code_from_url(response.url)
        course_title_full = response.css("h1.page-title::text").get()
        parsed_title, course_code_from_title = self.parse_title(course_title_full)

        final_course_code = course_code_from_url or course_code_from_title
        if not final_course_code:
            self.log(
                f"CRITICAL: Could not determine course code for URL: {response.url}"
            )
            return  # Skip this course if no code can be found

        # --- BASIC COURSE INFO ---
        credits_val = response.css(
            "div.courseblock div.detail-credits span.value::text"
        ).get()
        offered_by_val = response.css(
            "div.courseblock div.detail-offered_by span.value::text"
        ).get()
        terms_offered_val = response.css(
            "div.courseblock div.detail-terms_offered span.value::text"
        ).get()

        description = self.get_description(response)

        faculty_info = self.parse_faculty(offered_by_val)

        # --- COMPLEX NOTE PARSING (Prereqs, Coreqs, etc.) ---
        note_list_items = response.xpath(
            "//div[contains(@class, 'courseblock')]//div[contains(@class, 'detail-note_text')]//ul/li"
        )

        prereqs, coreqs, restricts, instructors, hours, other_notes = (
            self.parse_note_list(note_list_items)
        )

        # --- YIELD FINAL STRUCTURED DATA ---
        course_data = {
            "url": response.url,
            "code": final_course_code,
            "title": parsed_title,
            "credits": credits_val.strip() if credits_val else None,
            "department_full": offered_by_val.strip() if offered_by_val else None,
            "faculty": faculty_info,
            "terms_offered": terms_offered_val.strip() if terms_offered_val else None,
            "description": description,
            "prerequisites_raw": "; ".join(prereqs) if prereqs else None,
            "corequisites_raw": "; ".join(coreqs) if coreqs else None,
            "restrictions_raw": "; ".join(restricts) if restricts else None,
            "hours_info": hours.strip() if hours else None,
            "instructors_raw": "; ".join(instructors) if instructors else None,
            "other_notes": "; ".join(other_notes) if other_notes else None,
        }
        yield course_data

    # --- HELPER METHODS FOR CLEANER PARSING ---

    def get_course_code_from_url(self, url):
        """Extracts the course code from the URL, which is often the most reliable source."""
        try:
            path_segments = [seg for seg in url.split("/") if seg]
            if path_segments[-1] == "index.html":
                return path_segments[-2].upper()
            else:
                return path_segments[-1].upper()
        except IndexError:
            self.log(f"Could not parse course code from URL: {url}")
            return None

    def parse_title(self, course_title_full):
        """Parses the full H1 title to extract a clean title and a course code."""
        if not course_title_full:
            return None, None

        course_title_full = course_title_full.strip()
        title_match = re.match(
            r"([A-Z]{4}\s*\d{3}[A-Z\d]*)\.?\s*(.*)", course_title_full
        )
        if title_match:
            course_code = title_match.group(1).replace(" ", "-")
            clean_title = title_match.group(2).strip().rstrip(".")
            return clean_title, course_code
        return course_title_full, None

    def get_description(self, response):
        """Extracts the course description."""
        description_parts = response.css(
            "div.courseblock div.section--description div.section__content ::text"
        ).getall()
        description = " ".join(
            part.strip() for part in description_parts if part.strip()
        ).strip()
        if not description:  # Fallback
            description_parts = response.css(
                "div.courseblock div.section--description p::text"
            ).getall()
            description = " ".join(
                part.strip() for part in description_parts if part.strip()
            ).strip()
        return description if description else None

    def parse_faculty(self, offered_by_val):
        """Parses the faculty name from the 'Offered by' string."""
        if not offered_by_val:
            return None
        faculty_match = re.search(r"\(([^)]+Faculty[^)]+)\)", offered_by_val)
        return faculty_match.group(1) if faculty_match else None

    def parse_note_list(self, note_list_items):
        """Parses the unordered list for prerequisites, corequisites, etc."""
        prereqs, coreqs, restricts, instructors, other_notes = [], [], [], [], []
        hours = None

        for li in note_list_items:
            item_text_parts = li.xpath(".//text()").getall()
            item_text = " ".join(
                part.strip() for part in item_text_parts if part.strip()
            ).strip()
            item_text_lower = item_text.lower()

            if not item_text:
                continue

            # --- INTELLIGENT SPLITTING LOGIC ---
            if item_text_lower.startswith("prerequisite"):
                # Clean the initial label
                content = re.sub(
                    r"^[Pp]rerequisite(?:s)?\s*:\s*", "", item_text, flags=re.IGNORECASE
                ).strip()

                # Regex to find embedded corequisite keywords
                split_keywords = [
                    "pre/co-requisite",
                    "pre-co-requisite",
                    "pre co-requisite",
                    "corequisite",
                    "co-requisite",
                ]
                pattern = re.compile(
                    r"(.*?)(\b(?:" + "|".join(split_keywords) + r")s?:?\b)(.*)",
                    re.IGNORECASE | re.DOTALL,
                )
                match = pattern.search(content)

                if match:  # Found an embedded corequisite
                    prereq_part = match.group(1).strip().rstrip(".").rstrip(";")
                    coreq_part = match.group(3).strip()
                    if prereq_part:
                        prereqs.append(prereq_part)
                    if coreq_part:
                        coreqs.append(coreq_part)
                else:  # No embedded corequisite found
                    prereqs.append(content)

            elif item_text_lower.startswith(
                "corequisite"
            ) or item_text_lower.startswith("pre/co-requisite"):
                content = re.sub(
                    r"^(?:[Cc]orequisite(?:s)?|[Pp]re-\/[Cc]o-requisite(?:s)?)\s*:\s*",
                    "",
                    item_text,
                    flags=re.IGNORECASE,
                ).strip()
                coreqs.append(content)

            elif item_text_lower.startswith(
                "restriction"
            ) or item_text_lower.startswith("restrion"):
                content = re.sub(
                    r"^[Rr]estrictions?(?:\(s\))?\s*:\s*|^[Rr]estrion(?:s)?\s*:\s*",
                    "",
                    item_text,
                    flags=re.IGNORECASE,
                ).strip()
                restricts.append(content)

            elif re.match(r"^\(\s*\d+\s*-\s*\d+\s*-\s*\d+\s*\)$", item_text):
                hours = item_text

            elif item_text_lower.startswith("instructor"):
                content = re.sub(
                    r"^[Ii]nstructor(?:s)?\s*:\s*", "", item_text, flags=re.IGNORECASE
                ).strip()
                instructors.append(content)

            elif not item_text_lower.startswith("terms offered:"):
                other_notes.append(item_text)

        return prereqs, coreqs, restricts, instructors, hours, other_notes
