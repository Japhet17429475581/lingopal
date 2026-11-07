"""Run against a local ALLOW_DEV_AUTH=true server. Uses installed Chrome."""
import csv
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "artifacts"
OUTPUT.mkdir(exist_ok=True)
questions = {row["id"]: json.loads(row["payload"]) for row in csv.DictReader((ROOT / "data/grammar_questions.csv").open(encoding="utf-8"))}


def check_width(page):
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), "Horizontal overflow"


def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=os.getenv("BROWSER_CHANNEL", "chrome"), headless=True)
        for name, width, height in [("desktop", 1440, 1080), ("mobile", 390, 844), ("narrow", 320, 720)]:
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            errors, failures = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: failures.append(f"{response.status}: {response.url}") if "/api/" in response.url and response.status >= 400 else None)
            page.goto("http://127.0.0.1:3000", wait_until="networkidle")
            if page.locator("#welcome-screen").is_visible():
                page.locator("#start-app-btn").click()
            expect(page.locator(".quest-row").first).to_be_visible()
            check_width(page)
            page.screenshot(path=str(OUTPUT / f"{name}.png"), full_page=True)
            page.locator("#packSizeSlider").fill("5")
            page.locator("#startDeckBtn").click()
            page.wait_for_function("currentPack !== null")
            if page.locator("#btnFinishPack").is_visible():
                page.locator("#btnFinishPack").click()
                page.wait_for_function("currentPack === null")
                page.locator("#startDeckBtn").click()
            elif page.locator("#btnContinuePack").is_visible():
                page.locator("#btnContinuePack").click()
            expect(page.locator(".card")).to_be_visible()
            page.locator(".card").click()
            expect(page.locator(".card")).to_have_class("card flipped")
            page.locator("#btnKnow").click()
            page.wait_for_function("!swipeBusy")
            page.locator("#exitDeckBtn").click()
            page.locator('[data-tab="dictionary"]').click()
            expect(page.locator(".dict-item").first).to_be_visible()
            # Re-entering dictionary previously broke the due-count element.
            page.locator('[data-tab="cards"]').click()
            page.locator('[data-tab="dictionary"]').click()
            check_width(page)
            page.locator('[data-tab="grammar"]').click()
            page.wait_for_function("document.getElementById('grammarOnboarding').style.display === 'block' || document.querySelector('.grammar-topic')")
            if page.locator("#grammarOnboarding").is_visible():
                page.locator('.grammar-level-card[data-level="A1"]').click()
            expect(page.locator(".grammar-topic").first).to_be_visible()
            check_width(page)
            page.locator("#screen-grammar").evaluate("element => element.getAnimations().forEach(animation => animation.finish())")
            page.screenshot(path=str(OUTPUT / f"{name}-grammar.png"), full_page=True)
            page.locator(".grammar-topic").first.click()
            expect(page.locator(".grammar-lesson")).to_have_count(3)
            page.locator("#grammarStartTestBtn").click()
            expect(page.locator(".grammar-question-card")).to_be_visible()
            for index in range(6):
                question = page.evaluate("grammarQuestions[grammarQuestionIndex]")
                payload = questions[question["id"]]
                kind = question["question_type"]
                if kind == "constructor":
                    words = question["payload"]["words"]
                    used = set()
                    for word in payload["correct_order"]:
                        position = next(i for i, candidate in enumerate(words) if candidate == word and i not in used)
                        used.add(position)
                        page.locator(f'[data-option-index="{position}"]').click()
                    page.locator("#checkConstructor").click()
                elif kind == "boolean":
                    page.locator(f'[data-option-index="{0 if payload["correct"] else 1}"]').click()
                else:
                    position = question["payload"]["options"].index(payload["correct"])
                    page.locator(f'[data-option-index="{position}"]').click()
                expect(page.locator(".grammar-feedback.is-correct")).to_be_visible()
                page.locator("#grammarQuestionStage > .start-btn").click()
                if index < 5:
                    page.wait_for_function(f"grammarQuestionIndex === {index + 1} && !grammarBusy")
            expect(page.locator(".grammar-result-card")).to_be_visible()
            check_width(page)
            page.screenshot(path=str(OUTPUT / f"{name}-result.png"), full_page=True)
            page.locator('[data-tab="linguaplay"]').click()
            expect(page.locator(".book-card").first).to_be_visible()
            page.locator(".book-card").first.click()
            expect(page.locator("#bookPageCounter")).not_to_be_empty()
            assert page.locator(".reader-word").count() > 5
            page.locator("#bookNextPage").click()
            check_width(page)
            page.screenshot(path=str(OUTPUT / f"{name}-reader.png"), full_page=True)
            page.locator("#bookReaderBack").click()
            page.locator('[data-tab="profile"]').click()
            expect(page.locator(".profile-stat-tile")).to_have_count(4)
            page.locator('.theme-swatch[data-theme="siesta"]').click()
            assert page.locator("html").get_attribute("data-app-theme") == "siesta"
            page.locator('.theme-swatch[data-theme="madrid"]').click()
            check_width(page)
            page.locator('[data-tab="assistant"]').click()
            expect(page.locator(".chat-starter-btn")).to_have_count(6)
            check_width(page)
            assert not errors, errors
            assert not failures, failures
            print(f"PASS {name}: cards, dictionary, grammar test, reader, profile, themes, chat; no JS/API errors")
            page.close()
        browser.close()


if __name__ == "__main__":
    run()
