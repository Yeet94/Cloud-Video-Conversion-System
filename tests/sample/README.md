# Sample video for testing
# This file provides instructions for creating a test video

To test the video conversion system, you need a sample video file.

## Option 1: Use FFmpeg to create a test video

```bash
# Create a 10-second test video with color bars
ffmpeg -f lavfi -i testsrc=duration=10:size=1280x720:rate=30 \
       -f lavfi -i sine=frequency=1000:duration=10 \
       -c:v libx264 -c:a aac \
       -pix_fmt yuv420p \
       test_video.mp4
```

## Option 2: Download a sample video

You can use the Big Buck Bunny short clip:
- https://sample-videos.com/
- https://file-examples.com/index.php/sample-video-files/

## Testing the System

1. Start the services:
   ```bash
   docker-compose up -d
   ```

2. Wait for all services to be healthy:
   ```bash
   docker-compose ps
   ```

3. Request an upload URL:
   ```bash
   curl -X POST http://localhost:8000/upload/request \
     -H "Content-Type: application/json" \
     -d '{"filename": "test_video.mp4", "content_type": "video/mp4"}'
   ```

4. Upload the video using the returned URL:
   ```bash
   curl -X PUT "UPLOAD_URL" \
     -H "Content-Type: video/mp4" \
     --data-binary @test_video.mp4
   ```

5. Create a conversion job:
   ```bash
   curl -X POST http://localhost:8000/jobs \
     -H "Content-Type: application/json" \
     -d '{"input_path": "OBJECT_PATH", "output_format": "mp4"}'
   ```

6. Check job status:
   ```bash
   curl http://localhost:8000/jobs/JOB_ID
   ```

7. Download the converted video:
   ```bash
   curl http://localhost:8000/download/JOB_ID
   ```
