#!/usr/bin/env python3
"""
Export Excalidraw JSON file to PNG using headless browser.
"""
import asyncio
import json
import os
import base64
from playwright.async_api import async_playwright


async def export_excalidraw_to_png(input_file: str, output_file: str = None, scale: int = 2):
    """
    Export an Excalidraw JSON file to PNG via excalidraw.com

    Args:
        input_file: Path to the .excalidraw.json file
        output_file: Output PNG path (default: same name with .png)
        scale: Export scale (1, 2, or 3). Default is 2 for good quality.
    """
    if output_file is None:
        base = os.path.splitext(input_file)[0]
        if base.endswith('.excalidraw'):
            base = base[:-11]
        output_file = base + '.png'

    with open(input_file, 'r', encoding='utf-8') as f:
        excalidraw_data = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            accept_downloads=True
        )

        # Mock File System Access API
        await context.add_init_script('''
            window.__savedBlobData = null;
            Object.defineProperty(window, 'showSaveFilePicker', {
                value: async function(options) {
                    return {
                        createWritable: async function() {
                            return {
                                write: async function(blob) {
                                    const arrayBuffer = await blob.arrayBuffer();
                                    const uint8Array = new Uint8Array(arrayBuffer);
                                    let binary = '';
                                    for (let i = 0; i < uint8Array.length; i++) {
                                        binary += String.fromCharCode(uint8Array[i]);
                                    }
                                    window.__savedBlobData = btoa(binary);
                                },
                                close: async function() {}
                            };
                        }
                    };
                },
                writable: false,
                configurable: false
            });
        ''')

        page = await context.new_page()

        print("Opening excalidraw.com...")
        await page.goto('https://excalidraw.com/')
        await page.wait_for_selector('canvas', timeout=30000)
        await asyncio.sleep(3)

        print("Importing JSON data...")
        await page.evaluate('''async (data) => {
            const jsonStr = JSON.stringify(data);
            const blob = new Blob([jsonStr], { type: 'application/json' });
            const file = new File([blob], 'import.excalidraw.json', { type: 'application/json' });
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            const canvas = document.querySelector('canvas');
            canvas.dispatchEvent(new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer }));
            canvas.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer }));
            canvas.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer }));
        }''', excalidraw_data)
        await asyncio.sleep(2)
        print("Import complete.")

        print("Opening export dialog...")
        await page.keyboard.press('Control+Shift+e')
        await asyncio.sleep(2)

        # Select scale using Playwright's native click (better for React apps)
        if scale in [2, 3]:
            scale_text = f"{scale}×"
            print(f"Selecting scale: {scale_text}")

            # Find and click using Playwright locator
            try:
                scale_locator = page.locator(f'.RadioGroup__choice:has-text("{scale_text}")')
                await scale_locator.click()
                print(f"Clicked {scale}x scale button")
                await asyncio.sleep(2)
            except Exception as e:
                print(f"Failed to click scale button: {e}")

        # Click PNG button using Playwright
        print("Clicking PNG button...")
        await page.locator('button:has-text("PNG")').click()
        await asyncio.sleep(3)

        # Get the saved blob data
        png_data = await page.evaluate('() => window.__savedBlobData')
        if png_data:
            print(f"Got blob data, length: {len(png_data)}")
            download_path = os.path.abspath(output_file)
            with open(download_path, 'wb') as f:
                f.write(base64.b64decode(png_data))
            print(f"Saved PNG to: {download_path}")
        else:
            print("No blob captured. Falling back to preview canvas...")
            png_data = await page.evaluate('''() => {
                const modal = document.querySelector('.ImageExportModal');
                if (modal) {
                    const canvas = modal.querySelector('canvas');
                    if (canvas) {
                        return canvas.toDataURL('image/png').split(',')[1];
                    }
                }
                return null;
            }''')

            if png_data:
                download_path = os.path.abspath(output_file)
                with open(download_path, 'wb') as f:
                    f.write(base64.b64decode(png_data))
                print(f"Saved PNG from preview to: {download_path}")
            else:
                print("Could not extract PNG")
                return None

        await browser.close()

    return output_file


async def main():
    import sys
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'vllm_architecture.excalidraw.json'
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    scale = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    result = await export_excalidraw_to_png(input_file, output_file, scale)
    print(f"Export complete: {result}")


if __name__ == '__main__':
    asyncio.run(main())
