import logging
import requests
from moviepy import VideoFileClip, concatenate_videoclips
from utils.retry import download_retry


@download_retry
def download_video(url, save_path):
    try:
        logging.info(f"正在从 {url} 下载视频到 {save_path}")

        response = requests.get(url, stream=True, timeout=(10, 300))
        response.raise_for_status()  # 检查请求是否成功
    
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logging.info(f"视频已成功下载到 {save_path}")
    
    except Exception as e:
        logging.error(f"下载视频出错: {e}")
        raise e


def concatenate_video_files(video_paths, output_path, codec="libx264", preset="medium"):
    """拼接视频文件，即使在失败时也释放每个 ffmpeg 读取器。

    每个 VideoFileClip 都会持有一个 ffmpeg 子进程和文件句柄，直到被关闭；
    若发生泄漏，在长时间的多场景任务中会耗尽文件描述符。
    """
    clips = []
    final = None
    try:
        for path in video_paths:
            clips.append(VideoFileClip(path))
        final = concatenate_videoclips(clips)
        final.write_videofile(output_path, codec=codec, preset=preset)
    finally:
        if final is not None:
            final.close()
        for clip in clips:
            clip.close()
    return output_path
