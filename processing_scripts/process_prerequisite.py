import json
import os
import asyncio  # Added for asyncio operations
import time  # Retained for overall timing, but not for per-request delay
import logging  # Added for error logging if needed, though print is mostly used
from dotenv import load_dotenv

# Import from the new parallel requester script
from parallel_gemini_requester import process_prompts_concurrently, DEFAULT_MODEL_NAME

# --- Setup and Configuration ---
load_dotenv()  # Ensures .env from parallel_gemini_requester is also loaded if not already

# GOOGLE_API_KEY and genai model setup are now primarily handled by parallel_gemini_requester.py
# If this script still needs to make *synchronous* calls for other reasons,
# the genai setup could be retained. For now, we assume all LLM calls go via parallel_gemini_requester.

# Load the comprehensive prompt template
PROMPT_TEMPLATE_PATH = "llm_batch_prompt_template.txt"
try:
    with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        PROMPT_TEMPLATE = f.read()
except FileNotFoundError:
    raise FileNotFoundError(
        f"Error: Prompt template file not found at {PROMPT_TEMPLATE_PATH}"
    )


def build_batch_prompt(prereq_text, coreq_text):
    """Builds the full prompt string for the LLM."""
    input_data = {"prerequisite_text": prereq_text, "corequisite_text": coreq_text}
    # Ensure consistent JSON string for the prompt payload part
    input_json_string = json.dumps(input_data)  # Compact JSON for prompt
    return (
        PROMPT_TEMPLATE + "\n" + input_json_string
    )  # Ensure template and JSON are clearly separated


def save_data(data, filepath):
    """Saves data to a JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


async def process_courses(input_filepath, output_filepath):
    """Processes courses by sending their prerequisite/corequisite text to Gemini API in parallel."""
    # Initialize processed_courses_map early so it's always available for the finally block
    processed_courses_map = {}
    newly_processed_count = 0  # Keep track of courses processed in the current run

    try:
        # Load existing processed data first
        if os.path.exists(output_filepath):
            try:
                with open(output_filepath, "r", encoding="utf-8") as f:
                    loaded_processed_courses = json.load(f)
                for course in loaded_processed_courses:
                    if course.get("code"):
                        processed_courses_map[course["code"]] = course
                print(f"--- RESUMING ---")
                print(f"Loaded {len(processed_courses_map)} already processed courses.")
                print("-" * 20)
            except (json.JSONDecodeError, IOError) as e:
                print(
                    f"Warning: Could not load existing output file '{output_filepath}'. Starting from scratch. Error: {e}"
                )
                processed_courses_map = {}  # Ensure it's an empty dict if loading fails

        # Load all course data to be processed
        try:
            with open(input_filepath, "r", encoding="utf-8") as f:
                all_courses_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading input file '{input_filepath}': {e}")
            # If input file fails to load, we might still want to save the (potentially empty) processed_courses_map
            # This is handled by the finally block.
            return

        courses_to_process = []
        prompts_for_api = []
        course_prompt_mapping = []  # To map responses back to courses

        print(f"Preparing prompts for {len(all_courses_data)} total courses...")
        for course_data in all_courses_data:
            course_code = course_data.get("code")
            if not course_code:
                print(
                    f"Skipping course due to missing code: {course_data.get('title', 'N/A')}"
                )
                continue

            if course_code in processed_courses_map and not processed_courses_map[
                course_code
            ].get("parsing_error"):
                continue

            prereqs_raw = course_data.get("prerequisites_raw", "")
            coreqs_raw = course_data.get("corequisites_raw", "")

            prompt_text = build_batch_prompt(prereqs_raw, coreqs_raw)
            prompts_for_api.append(prompt_text)
            course_prompt_mapping.append(course_data)

        if not prompts_for_api:
            print("No new courses or prompts to process based on current data.")
            # Even if no new prompts, save in case the loaded data was modified or to ensure file exists
            # This is effectively handled by the finally block ensuring a save happens.
            return  # Exit early, finally block will still run

        print(
            f"Streaming {len(prompts_for_api)} prompts to Gemini API in parallel (model: {DEFAULT_MODEL_NAME})..."
        )
        start_time = time.time()
        total_prompts_sent = len(prompts_for_api)
        responses_processed_count = 0

        async for api_result in process_prompts_concurrently(
            prompts_for_api, model_name=DEFAULT_MODEL_NAME
        ):
            responses_processed_count += 1
            original_prompt_idx = api_result.get("index")

            if original_prompt_idx is None:
                # Using logging for errors from the async generator is good practice
                logging.error(
                    f"API result missing 'index': {api_result}. Skipping this result."
                )
                continue

            if not (0 <= original_prompt_idx < len(course_prompt_mapping)):
                logging.error(
                    f"Invalid 'index' {original_prompt_idx} in API result. Max index is {len(course_prompt_mapping)-1}. Result: {api_result}. Skipping."
                )
                continue

            course_to_update = course_prompt_mapping[original_prompt_idx]
            course_code = course_to_update.get("code")

            print(
                f"\nReceived response {responses_processed_count}/{total_prompts_sent}. Processing course: {course_code} (Original Prompt ID: {original_prompt_idx+1}) - {course_to_update.get('title', '')}"
            )
            print(
                f"  Original Prompt (summary): {api_result.get('prompt', 'N/A')[:100]}..."
            )

            if api_result.get("error"):
                print(
                    f"  LLM/PARSING ERROR for {course_code}: {api_result['error']} (Status: {api_result.get('status_code')})"
                )
                course_to_update["parsing_error"] = (
                    f"{api_result['error']} (Status: {api_result.get('status_code')})"
                )
                if "prerequisites_parsed" not in course_to_update:
                    course_to_update["prerequisites_parsed"] = [
                        {
                            "type": "TEXTUAL",
                            "text": course_to_update.get("prerequisites_raw", "None"),
                        }
                    ]
                if "corequisites_parsed" not in course_to_update:
                    course_to_update["corequisites_parsed"] = [
                        {
                            "type": "TEXTUAL",
                            "text": course_to_update.get("corequisites_raw", "None"),
                        }
                    ]
            else:
                try:
                    parsed_llm_json = json.loads(api_result["response"])
                    course_to_update["prerequisites_parsed"] = parsed_llm_json.get(
                        "parsed_prerequisites", []
                    )
                    course_to_update["corequisites_parsed"] = parsed_llm_json.get(
                        "parsed_corequisites", []
                    )
                    course_to_update.pop("parsing_error", None)
                    print(f"  Successfully parsed LLM response for {course_code}.")
                except json.JSONDecodeError as e:
                    print(
                        f"  JSONDecodeError parsing LLM response for {course_code}: {e}"
                    )
                    print(f"  Raw LLM Response: {api_result['response'][:500]}...")
                    course_to_update["parsing_error"] = (
                        f"JSONDecodeError: {e}. Raw response: {api_result['response'][:200]}..."
                    )
                    course_to_update["prerequisites_parsed"] = [
                        {
                            "type": "TEXTUAL",
                            "text": course_to_update.get("prerequisites_raw", "None"),
                        }
                    ]
                    course_to_update["corequisites_parsed"] = [
                        {
                            "type": "TEXTUAL",
                            "text": course_to_update.get("corequisites_raw", "None"),
                        }
                    ]
                except Exception as e:
                    print(
                        f"  Unexpected error parsing LLM response for {course_code}: {e}"
                    )
                    course_to_update["parsing_error"] = (
                        f"Unexpected parsing error: {e}. Raw response: {api_result['response'][:200]}..."
                    )
                    course_to_update["prerequisites_parsed"] = [
                        {
                            "type": "TEXTUAL",
                            "text": course_to_update.get("prerequisites_raw", "None"),
                        }
                    ]
                    course_to_update["corequisites_parsed"] = [
                        {
                            "type": "TEXTUAL",
                            "text": course_to_update.get("corequisites_raw", "None"),
                        }
                    ]

            processed_courses_map[course_code] = course_to_update
            newly_processed_count += (
                1  # newly_processed_count tracks courses updated in this session
            )

            if newly_processed_count > 0 and newly_processed_count % 25 == 0:
                print(
                    f"\n...Saving progress ({len(processed_courses_map)} total courses in map, {newly_processed_count} new/updated this run)..."
                )
                save_data(list(processed_courses_map.values()), output_filepath)
                print(f"Progress saved at {time.strftime('%Y-%m-%d %H:%M:%S')}")

        end_time = time.time()
        print(
            f"\n--- NORMAL COMPLETION OF STREAMING LOOP --- ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        )
        print(
            f"Processed {responses_processed_count}/{total_prompts_sent} responses in {end_time - start_time:.2f} seconds."
        )

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected. Preparing to save progress...")
        # Allow finally block to handle saving.
        # asyncio.run() typically handles KeyboardInterrupt by cancelling the task,
        # which should then trigger the finally block.
    except asyncio.CancelledError:
        print(
            "\nAsyncio task was cancelled (possibly due to KeyboardInterrupt or other shutdown signal). Preparing to save progress..."
        )
        # Allow finally block to handle saving.
    except Exception as e:
        # Catch any other unexpected exceptions during the main processing.
        print(
            f"\nAn unexpected error occurred in process_courses: {type(e).__name__} - {e}"
        )
        import traceback

        traceback.print_exc()
        print("Preparing to save whatever progress was made due to unexpected error...")
        # Allow finally block to handle saving.
    finally:
        print(
            f"\n--- ATTEMPTING SAVE (FINALLY BLOCK) --- ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        )
        if isinstance(processed_courses_map, dict) and processed_courses_map:
            save_data(list(processed_courses_map.values()), output_filepath)
            print(
                f"Processing finished or interrupted. Total of {len(processed_courses_map)} courses saved to '{output_filepath}'."
            )
            if newly_processed_count > 0:
                print(
                    f"{newly_processed_count} courses had their LLM data processed/updated in this run before exit/completion."
                )
        elif isinstance(processed_courses_map, dict) and not processed_courses_map:
            print(
                "No courses were in the processed_courses_map to save (it was empty). Output file may be empty or unchanged if it existed."
            )
            # Optionally, still call save_data to ensure an empty list is written if that's desired for an empty map
            # save_data([], output_filepath)
        else:
            print(
                "Could not save from finally block: processed_courses_map was not a dictionary or not initialized as expected."
            )


if __name__ == "__main__":
    raw_data_path = "../data/mcgill_courses_raw.json"
    processed_data_path = "../data/mcgill_courses_processed.json"

    # For Windows, if you encounter issues with aiohttp and the default event loop policy:
    # if os.name == 'nt':
    # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(process_courses(raw_data_path, processed_data_path))
