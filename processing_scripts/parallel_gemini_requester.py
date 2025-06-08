# parallel_gemini_requester.py

import asyncio
import aiohttp
import os
import json
import logging
import time
from dotenv import load_dotenv
from typing import List, Dict, Optional, AsyncGenerator

# --- Configuration ---
# Load environment variables from .env file in the script's directory
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path)

API_KEY = os.getenv("GEMINI_API_KEY")

# Model name updated to match previous configuration in process_prerequisite.py
# User should verify this is the correct and desired model for Gemini 2.5 Flash supporting JSON output.
DEFAULT_MODEL_NAME = "gemini-2.0-flash"
GEMINI_API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

# User mentioned 1000 RPM. (1000 requests / 60 seconds = ~16.67 RPS)
# MAX_CONCURRENT_REQUESTS controls simultaneous connections.
# Adjust based on average request latency and actual rate limit behavior.
MAX_CONCURRENT_REQUESTS = 14  # Adjustable
RETRY_ATTEMPTS = 3  # Max retries for rate limits or transient errors
INITIAL_RETRY_DELAY_SECONDS = 5  # Initial delay for retries, increases exponentially
REQUEST_TIMEOUT_SECONDS = 60  # Timeout for each API request

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def send_gemini_request(
    session, prompt_text, api_key, semaphore, model_name, index
):
    """
    Sends a single prompt to the Gemini API, handles retries, and respects semaphore.

    Args:
        session (aiohttp.ClientSession): The HTTP session.
        prompt_text (str): The text prompt to send to the API.
        api_key (str): The API key for authentication.
        semaphore (asyncio.Semaphore): Semaphore to limit concurrent requests.
        model_name (str): The specific Gemini model to use (e.g., 'gemini-2.5-flash').
        index (int): The original index of the prompt.

    Returns:
        dict: A dictionary containing the original prompt, response text (if successful),
              any error message, and the HTTP status code.
    """
    await semaphore.acquire()  # Wait for an available slot from the semaphore
    try:
        api_url = GEMINI_API_URL_TEMPLATE.format(model_name=model_name, api_key=api_key)

        # IMPORTANT: User should verify this request payload structure for Gemini 2.5 Flash.
        # Payload including generationConfig to ensure JSON response and other parameters
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {
                "temperature": 0.1,
                "top_p": 1.0,
                "top_k": 1,
                "maxOutputTokens": 8192,
                "response_mime_type": "application/json",
            },
        }
        headers = {"Content-Type": "application/json"}

        current_attempt = 0
        while current_attempt < RETRY_ATTEMPTS:
            try:
                logging.info(
                    f"Sending prompt (model: {model_name}, attempt {current_attempt + 1}/{RETRY_ATTEMPTS}): {prompt_text[:60]}..."
                )
                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
                ) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        # IMPORTANT: User should verify this response parsing logic.
                        try:
                            generated_text = (
                                response_data.get("candidates", [{}])[0]
                                .get("content", {})
                                .get("parts", [{}])[0]
                                .get("text", "")
                            )
                            if not generated_text and response_data.get("candidates"):
                                logging.warning(
                                    f"Extracted empty text for prompt '{prompt_text[:60]}...'. Check response structure. Full response: {json.dumps(response_data, indent=2)}"
                                )
                            elif not response_data.get("candidates"):
                                logging.warning(
                                    f"No 'candidates' field in response for prompt '{prompt_text[:60]}...'. Full response: {json.dumps(response_data, indent=2)}"
                                )

                            logging.info(
                                f"Successfully received response for prompt: {prompt_text[:60]}..."
                            )
                            return {
                                "prompt": prompt_text,
                                "response": generated_text,
                                "error": None,
                                "status_code": response.status,
                                "index": index,
                            }
                        except (IndexError, KeyError, TypeError) as e:
                            logging.error(
                                f"Error parsing response for prompt '{prompt_text[:60]}...': {e}. Response: {json.dumps(response_data, indent=2)}"
                            )
                            return {
                                "prompt": prompt_text,
                                "response": None,
                                "error": f"Response parsing error: {e}",
                                "status_code": response.status,
                                "index": index,
                            }

                    elif response.status == 429:  # Rate limit exceeded
                        retry_after_header = response.headers.get("Retry-After")
                        wait_time = INITIAL_RETRY_DELAY_SECONDS * (2**current_attempt)
                        if retry_after_header and retry_after_header.isdigit():
                            wait_time = max(
                                wait_time, int(retry_after_header)
                            )  # Use API suggested delay if available and longer

                        logging.warning(
                            f"Rate limit exceeded (429) for prompt: {prompt_text[:60]}.... Retrying in {wait_time}s. Attempt {current_attempt + 1}/{RETRY_ATTEMPTS}"
                        )
                        await asyncio.sleep(wait_time)
                        current_attempt += 1
                        if current_attempt >= RETRY_ATTEMPTS:
                            logging.error(
                                f"Max retries ({RETRY_ATTEMPTS}) reached for prompt: {prompt_text[:60]}... due to rate limiting (429)."
                            )
                            return {
                                "prompt": prompt_text,
                                "response": None,
                                "error": f"Max retries reached due to rate limiting (429) after {RETRY_ATTEMPTS} attempts",
                                "status_code": response.status,
                                "index": index,
                            }
                        # Continue to next attempt in the while loop

                    else:  # Other HTTP errors
                        error_text = await response.text()
                        logging.error(
                            f"API request failed for prompt '{prompt_text[:60]}...' with status {response.status}: {error_text}"
                        )
                        return {
                            "prompt": prompt_text,
                            "response": None,
                            "error": f"API Error {response.status}: {error_text}",
                            "status_code": response.status,
                            "index": index,
                        }

            except aiohttp.ClientConnectorError as e:  # Network connection errors
                logging.error(
                    f"ClientConnectorError for prompt '{prompt_text[:60]}...' (attempt {current_attempt + 1}): {e}. Retrying if attempts left."
                )
                await asyncio.sleep(INITIAL_RETRY_DELAY_SECONDS * (2**current_attempt))
                current_attempt += 1
                if current_attempt >= RETRY_ATTEMPTS:
                    logging.error(
                        f"Max retries reached for prompt '{prompt_text[:60]}...' due to ClientConnectorError."
                    )
                    return {
                        "prompt": prompt_text,
                        "response": None,
                        "error": f"ClientConnectorError after {RETRY_ATTEMPTS} retries: {e}",
                        "status_code": "N/A - Connection Error",
                        "index": index,
                    }

            except asyncio.TimeoutError:  # Request timeout
                logging.error(
                    f"Request timed out for prompt '{prompt_text[:60]}...' (attempt {current_attempt + 1}). Retrying if attempts left."
                )
                await asyncio.sleep(INITIAL_RETRY_DELAY_SECONDS * (2**current_attempt))
                current_attempt += 1
                if current_attempt >= RETRY_ATTEMPTS:
                    logging.error(
                        f"Max retries reached for prompt '{prompt_text[:60]}...' due to timeout."
                    )
                    return {
                        "prompt": prompt_text,
                        "response": None,
                        "error": f"Request timed out after {RETRY_ATTEMPTS} retries",
                        "status_code": "N/A - Timeout",
                        "index": index,
                    }

            except aiohttp.ClientError as e:  # Other aiohttp client errors
                logging.error(
                    f"AIOHTTP ClientError for prompt '{prompt_text[:60]}...' (attempt {current_attempt + 1}): {e} (Type: {type(e)}). This type of error is not automatically retried."
                )
                return {
                    "prompt": prompt_text,
                    "response": None,
                    "error": f"AIOHTTP ClientError: {e}",
                    "status_code": "N/A - Client Error",
                    "index": index,
                }

        # This line should ideally not be reached if logic within loop is correct,
        # as all paths (success, retryable error with max retries, non-retryable error) should return.
        # However, as a fallback:
        logging.error(
            f"Exited retry loop unexpectedly for prompt: {prompt_text[:60]}..."
        )
        return {
            "prompt": prompt_text,
            "response": None,
            "error": "Exited retry loop unexpectedly",
            "status_code": "N/A - Loop Exit",
            "index": index,
        }

    except Exception as e:  # Catch-all for unexpected errors before or during the loop
        logging.exception(
            f"An unexpected error occurred processing prompt '{prompt_text[:60]}...': {e}"
        )
        return {
            "prompt": prompt_text,
            "response": None,
            "error": f"UnexpectedError: {str(e)}",
            "status_code": "N/A - Unexpected",
            "index": index,
        }
    finally:
        semaphore.release()  # Crucial: ensure semaphore is always released


async def process_prompts_concurrently(
    prompts: List[str],
    model_name: str = DEFAULT_MODEL_NAME,
    api_key: Optional[str] = None,
) -> AsyncGenerator[Dict, None]:
    effective_api_key = api_key or os.getenv("GEMINI_API_KEY")
    if not effective_api_key:
        logging.error("GEMINI_API_KEY not found.")
        for i, prompt_text in enumerate(prompts):
            yield {
                "prompt": prompt_text,
                "response": None,
                "error": "GEMINI_API_KEY not found.",
                "status_code": None,
                "index": i,  # Original index of the prompt
            }
        return

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    timeout_config = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

    async with aiohttp.ClientSession(timeout=timeout_config) as session:
        tasks = []
        for i, prompt_text in enumerate(prompts):
            task = send_gemini_request(
                session, prompt_text, effective_api_key, semaphore, model_name, i
            )
            tasks.append(task)

        for future in asyncio.as_completed(tasks):
            try:
                result = (
                    await future
                )  # This result is the dictionary from send_gemini_request
                yield result
            except asyncio.CancelledError:
                logging.info(
                    "A send_gemini_request task was cancelled. Propagating cancellation."
                )
                raise  # Re-raise CancelledError to stop the generator and allow proper handling upstream
            except Exception as e:
                # This case should be rare if send_gemini_request's internal error handling is robust.
                # It catches unexpected errors from within a task that weren't turned into a dict by send_gemini_request.
                logging.error(
                    f"Unhandled exception from a send_gemini_request task via as_completed: {e}",
                    exc_info=True,
                )
                # To prevent crashing the entire process, we log the error and continue.
                # The consumer will not receive a result for this specific failed task.
                # Consider if a placeholder error dict should be yielded; for now, it's skipped.
                pass


async def main():
    """
    Main function to demonstrate parallel processing of prompts.
    """
    sample_prompts = [
        "Explain the theory of relativity in simple terms.",
        "What is the capital of France?",
        "Write a short poem about a rainy day.",
        "Summarize the plot of 'To Kill a Mockingbird'.",
        "What are the main benefits of using asyncio in Python?",
        "Translate 'hello world' into Spanish.",
        "What is the chemical formula for water?",
        "Who painted the Mona Lisa?",
        "Describe the process of photosynthesis.",
        "What are three common uses for Python programming language?",
    ]
    # To test rate limits and concurrency, increase the number of prompts:
    # sample_prompts.extend([f"This is test prompt number {i} to check concurrency and rate limiting." for i in range(1, MAX_CONCURRENT_REQUESTS * 3 + 1)])

    logging.info(
        f"Starting to process {len(sample_prompts)} prompts concurrently with model '{DEFAULT_MODEL_NAME}'..."
    )
    start_time = time.time()

    all_responses = await process_prompts_concurrently(
        sample_prompts, model_name=DEFAULT_MODEL_NAME
    )

    end_time = time.time()
    processing_duration = end_time - start_time
    logging.info(
        f"Finished processing all prompts in {processing_duration:.2f} seconds."
    )

    successful_responses_count = 0
    failed_responses_count = 0
    print("\n--- Processing Summary ---")
    for i, res in enumerate(all_responses):
        print(f"Result {i+1}:")
        print(
            f"  Prompt: '{res['prompt'][:70]}...'"
            + (" (truncated)" if len(res["prompt"]) > 70 else "")
        )
        if res.get("error"):
            print(f"  Status: FAILED (Code: {res.get('status_code', 'N/A')})")
            print(f"  Error: {res['error']}")
            failed_responses_count += 1
        else:
            print(f"  Status: SUCCESS (Code: {res.get('status_code')})")
            print(
                f"  Response: {res['response'][:100]}..."
                + (" (truncated)" if len(res.get("response", "")) > 100 else "")
            )
            successful_responses_count += 1
        print("---")

    logging.info(
        f"Overall Summary: {successful_responses_count} successful, {failed_responses_count} failed out of {len(all_responses)} prompts."
    )
    if failed_responses_count > 0:
        logging.warning("Some prompts failed. Check logs for details.")


if __name__ == "__main__":
    # For Windows, if you encounter issues with aiohttp and the default event loop policy:
    # if os.name == 'nt':
    #     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
