import asyncio
from playwright.async_api import async_playwright
import os
import getpass
from openpyxl import load_workbook
import subprocess


local_dir = os.path.dirname(os.path.abspath(__file__))

async def fetch_descriptions_list(url, username, password, debug_dir="./debug"):

    os.makedirs(debug_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # simple console / response logging
        #page.on("console", lambda msg: print(f"[console] {msg.type}: {msg.text}"))
        #page.on("response", lambda r: print(f"[response] {r.status} {r.url}"))

        await page.goto(url)
        await page.wait_for_load_state("networkidle")

        # debug: save the initial HTML and screenshot
        html = await page.content()
        open(f"{debug_dir}/01-page_start.html", "w", encoding="utf-8").write(html)
        await page.screenshot(path=f"{debug_dir}/01-start.png", full_page=True)

        # Try robust selectors and print counts
        selectors = [
            "#btnLogin",             # direct id selector for the input
            ".btnLogin.btnKey",      # both classes on same element
            ".btnLogin .btnKey",     # nested selector
        ]
        found = False
        for sel in selectors:
            try:
                count = await page.locator(sel).count()
            except Exception:
                count = 0
            print(f"Selector '{sel}' count = {count}")
            if count > 0:
                # wait until visible then click
                try:
                    await page.wait_for_selector(sel, state="visible", timeout=5000)

                    print("Start page loaded. Clicking on login...")

                    await page.locator(sel).first.click()
                    found = True
                    break
                except Exception as e:
                    print(f"Click with {sel} failed: {e}")

        if not found:
            print("No working selector found")
            await browser.close()
            return html, []
        
        # wait a bit for any navigation or JS actions
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            await page.wait_for_timeout(2000)

        print("Login page should be loaded now.")

        # save after state for inspection
        html = await page.content()
        open(f"{debug_dir}/01-page_login.html", "w", encoding="utf-8").write(html)
        await page.screenshot(path=f"{debug_dir}/02-login.png", full_page=True)

        # Do login
        try:
            await page.wait_for_selector("#login-form_username", state="visible", timeout=5000)
            await page.fill("#login-form_username", username)
        except Exception as e:
            print("Username field not found:", e)

        try:
            await page.wait_for_selector("#login-form_password", state="visible", timeout=5000)
            await page.fill("#login-form_password", password)
        except Exception as e:
            print("Password field not found:", e)

        # click the submit input
        try:
            await page.wait_for_selector("#login-submit-button", state="visible", timeout=5000)

            print ("Submitting login form...")

            await page.locator("#login-submit-button").click()
        except Exception as e:
            print("Submit button click failed:", e)
            await browser.close()
            return html, []

        # wait a bit for any navigation or JS actions
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            await page.wait_for_timeout(2000)

        print("Post-login page should be loaded now.")

        # save after state for inspection
        html = await page.content()
        open(f"{debug_dir}/03-page_main.html", "w", encoding="utf-8").write(html)
        await page.screenshot(path=f"{debug_dir}/03-main.png", full_page=True)

        # Click on administration
        # Find all elements with id ending in 'DepartmentAdmin'
        elements = await page.query_selector_all('[id$="DepartmentAdmin"]')
        ids = []
        for el in elements:
            el_id = await el.get_attribute("id")
            if el_id:
                ids.append(el_id)
        print("Found DepartmentAdmin ids:", ids)

        # wait for the department administration link and click it
        await page.wait_for_selector("#ctl13_hlDepartmentAdmin", state="visible", timeout=7000)
        print("Clicking department administration link...")
        await page.locator("#ctl13_hlDepartmentAdmin").first.click()
        # wait for navigation / JS to settle

        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            await page.wait_for_timeout(2000)

        # save admin page snapshot for debugging
        html = await page.content()
        open(f"{debug_dir}/04-page-dept_admin.html", "w", encoding="utf-8").write(html)
        await page.screenshot(path=f"{debug_dir}/04-dept_admin.png", full_page=True)
 
        # Download task descriptions

        # Get the selected option from the semester dropdown
        try:
            await page.wait_for_selector("#cphMain_ddlSemester", state="visible", timeout=5000)
            selected_option = await page.locator("#cphMain_ddlSemester option[selected]").text_content()
            print(f"Selected semester: {selected_option.strip() if selected_option else 'None'}")
        except Exception as e:
            print("Could not get selected semester:", e)

        semester = selected_option.strip() if selected_option else None
        if semester:
            semester = semester.replace(". ", "-")

        # Wait for the CSV export button to be visible and click it
        try:
            await page.wait_for_selector("#cphMain_hlExcel", state="visible", timeout=7000)
            print("Clicking CSV export button and waiting for download...")

            # async context manager must be used with `async with`
            async with page.expect_download() as download_info:
                await page.locator("#cphMain_hlExcel").click()

            download = await download_info.value
            download_path = os.path.join(local_dir, f"{semester}_TMIT.xlsx")
            await download.save_as(download_path)
            print(f"Downloaded file saved to {download_path}")

        except Exception as e:
            print("CSV export button click failed:", e)


        cookies = await context.cookies()
        await browser.close()
        return html, semester, cookies


async def fetch_description(url, cookies, save_dir, debug_dir="./debug"):

    os.makedirs(debug_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Set cookies
        await context.add_cookies(cookies)

        page = await context.new_page()

        # simple console / response logging
        #page.on("console", lambda msg: print(f"[console] {msg.type}: {msg.text}"))
        #page.on("response", lambda r: print(f"[response] {r.status} {r.url}"))

        print(f"Navigating to description URL: {url}")
        await page.goto(url)
        await page.wait_for_load_state("networkidle")

        # save the HTML and screenshot for inspection
        html = await page.content()
        open(os.path.join(debug_dir, f"05-page-student.html"), "w", encoding="utf-8").write(html)
        await page.screenshot(path=os.path.join(debug_dir, f"05-student.png"), full_page=True)

        # Find the div with class 'semester'
        locator = page.locator("div.semester li.pdf a")
        count = await locator.count()
        if count == 0:
            print("No download link element found")
            await browser.close()
            return False

        download_link = locator.first
        try:
            await download_link.wait_for(state="visible", timeout=5000)
            print("Clicking on the PDF download link...")
            async with page.expect_download() as download_info:
                await download_link.click()
            download = await download_info.value
            suggested_filename = download.suggested_filename
            save_path = os.path.join(save_dir, suggested_filename)
            await download.save_as(save_path)
            print(f"Downloaded file saved to {save_path}")
            await browser.close()
            return True
        except Exception as e:
            print("Download link not found or click failed:", e)
            await browser.close()
            return False

async def main():

    username = getpass.getuser("Enter username: ")
    password = getpass.getpass("Enter password: ")

    # Download xlsx file from the portal
    url = "https://diplomaterv.vik.bme.hu/hu/Login.aspx?ReturnUrl=%2fhu%2f&DirectLogin=true"
    html, semester, cookies = await fetch_descriptions_list(url, username, password)

    task_desc_path = os.path.join(local_dir, f"{semester}_TMIT.xlsx")
    if os.path.exists(task_desc_path):
        print(f"Task descriptions file exists at: {task_desc_path}")
    else:
        print("Task descriptions file was not downloaded.")
        exit(1)

    # Get the links to the task descriptions
    wb = load_workbook(filename = task_desc_path, read_only=True)
    sheet = wb.active

    urls = []

    r = 5
    while True:
        url = sheet['AW' + str(r)].value
        if (url == None):
            break
        if sheet['X' + str(r)].value == u"Feltöltve, tanszékvezetői jóváhagyásra vár":
            urls.append(url)
        r = r + 1

    print(f"Found {len(urls)} task description URLs needing approval.")

    # Downoad each task description
    desc_dir = "/data"
    os.makedirs(desc_dir, exist_ok=True)
    
    for i, url in enumerate(urls):
        ok = await fetch_description(url, cookies, desc_dir)

    # Set permissions so that the web server can read the files
    subprocess.run(["chown", "-R", "www-data:www-data", "/data"])

    # call create_db.py to update the database
    subprocess.run(["python3",
                    os.path.join(local_dir, "create_db.py"),
                    task_desc_path])
    # set permissions for the database
    subprocess.run(["chown", "-R", "www-data:www-data", "/db"])


asyncio.run(main())