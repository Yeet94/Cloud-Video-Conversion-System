import asyncio
import aiohttp

async def test_upload():
    async with aiohttp.ClientSession() as session:
        # Step 1: Get upload URL
        print("Step 1: Requesting upload URL...")
        async with session.post('http://localhost/api/upload/request', json={'filename':'test.mp4'}) as resp:
            print(f"Status: {resp.status}")
            data = await resp.json()
            print(f"Response: {data}")
            upload_url = data['upload_url']
            file_key = data.get('file_key') or data.get('object_path')
        
        # Step 2: Upload file
        print(f"\nStep 2: Uploading to {upload_url}")
        video_data = b'fake video data'
        try:
            async with session.put(upload_url, data=video_data) as resp:
                print(f"Upload status: {resp.status}")
                text = await resp.text()
                print(f"Upload response: {text[:200]}")
        except Exception as e:
            print(f"Upload error: {e}")
            return
        
        # Step 3: Create job
        print(f"\nStep 3: Creating job with file_key={file_key}")
        try:
            async with session.post('http://localhost/api/jobs', json={'input_path': file_key, 'output_format': 'mp4'}) as resp:
                print(f"Job creation status: {resp.status}")
                text = await resp.text()
                print(f"Job creation response: {text}")
        except Exception as e:
            print(f"Job creation error: {e}")

asyncio.run(test_upload())
