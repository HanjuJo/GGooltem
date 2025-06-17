import os
import json
import subprocess
from datetime import datetime
import whisper
import requests
from moviepy.editor import VideoFileClip
from pathlib import Path
import re
import threading
import collections # For word frequency counting
import google.generativeai as genai # Gemini API 임포트
import hmac
import hashlib
import base64
import time
import urllib.parse

class VideoProcessor:
    def __init__(self, stop_event: threading.Event = None, api_key: str = None):
        self.model = whisper.load_model("base")
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
        self.stop_event = stop_event if stop_event else threading.Event()
        
        # API 키는 인자로 전달받거나 환경 변수에서 로드
        self.api_key = api_key if api_key else os.environ.get("GOOGLE_API_KEY")
        # print(f"[DEBUG_INIT] VideoProcessor 초기화: self.api_key 설정됨: {self.api_key is not None}, 값 시작: {self.api_key[:5]}...") # 디버그 출력 제거

        # Gemini API를 위한 generation_config 설정
        self.generation_config = genai.GenerationConfig(
            temperature=0.9,
            max_output_tokens=1000,
            top_p=1.0,
            top_k=1
        )

        # 쿠팡 파트너스 API 키 설정
        self.coupang_access_key = os.environ.get("COUPANG_PARTNERS_ACCESS_KEY")
        self.coupang_secret_key = os.environ.get("COUPANG_PARTNERS_SECRET_KEY")
        if not self.coupang_access_key or not self.coupang_secret_key:
            print("경고: COUPANG_PARTNERS_ACCESS_KEY 또는 COUPANG_PARTNERS_SECRET_KEY 환경 변수가 설정되지 않았습니다.")

        # Gemini API 설정
        if not self.api_key:
            print("경고: GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다. Gemini API를 사용할 수 없습니다.")
            self.gemini_model = None
        else:
            try:
                genai.configure(api_key=self.api_key) # 환경 변수에서 가져온 키 사용
                self.gemini_model = genai.GenerativeModel("gemini-1.5-flash", generation_config=self.generation_config)
                # print(f"[DEBUG_INIT] Gemini 모델 초기화 성공: {self.gemini_model is not None}") # 디버그 출력 제거
            except Exception as e:
                print(f"[DEBUG_INIT] Gemini 모델 초기화 오류 발생: {e}") # 디버그 출력
                self.gemini_model = None

    def _check_stop_event(self):
        if self.stop_event.is_set():
            raise InterruptedError("작업이 중지되었습니다.")

    # Simple Korean stopwords (can be expanded)
    KOREAN_STOPWORDS = {
        '이', '그', '저', '것', '수', '등', '들', '와', '과', '을', '를', '은', '는', '도', '만', '하다',
        '에', '에서', '으로', '로', '에게', '께', '한테', '부터', '까지', '보다', '처럼', '만큼', '같이',
        '이것', '그것', '저것', '여기', '거기', '저기', '저쪽', '곳', '때', '면', '좀', '정말', '진짜',
        '아', '네', '예', '아니오', '응', '그래', '뭐', '어디', '누구', '언제', '왜', '어떻게', '하나', '두', '세', '네',
        '있다', '없다', '않다', '되다', '이다', '아니다', '좋다', '크다', '많다', '같다', '말하다', '보다', '가다', '오다',
        '주다', '받다', '쓰다', '읽다', '듣다', '먹다', '자다', '일어나다', '앉다', '서다', '알다', '모르다'
    }

    def _get_video_metadata(self, url):
        """yt-dlp를 사용하여 영상 메타데이터를 가져옵니다."""
        try:
            command = [
                "yt-dlp",
                "--dump-json",
                "--flat-playlist",  # For playlist URL, dump info for each video
                "--skip-download",
                url
            ]
            process = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
            metadata = json.loads(process.stdout)
            
            # If it's a playlist, metadata might contain 'entries'
            if 'entries' in metadata and isinstance(metadata['entries'], list):
                if len(metadata['entries']) > 0:
                    metadata = metadata['entries'][0] # Take the first entry if it's a list
                else:
                    return None # No entries found
            
            video_title = metadata.get('title', metadata.get('id', 'Unknown_Title'))
            video_id = metadata.get('id', 'Unknown_ID')
            uploader = metadata.get('uploader', metadata.get('channel', 'Unknown_Uploader'))
            duration = metadata.get('duration') # duration in seconds
            original_url = metadata.get('webpage_url', url)

            return {
                'video_title': video_title,
                'video_id': video_id,
                'uploader': uploader,
                'duration': duration,
                'url': original_url
            }
        except subprocess.CalledProcessError as e:
            print(f"메타데이터 가져오기 오류 (yt-dlp): {e.stderr}")
            return None
        except json.JSONDecodeError as e:
            print(f"메타데이터 JSON 파싱 오류: {e}")
            return None
        except Exception as e:
            print(f"메타데이터 가져오기 중 예상치 못한 오류 발생: {e}")
            return None

    def download_video_from_url(self, video_url):
        """URL에서 단일 영상 다운로드 (yt-dlp 사용)"""
        self._check_stop_event()
        try:
            # Step 1: Get video metadata
            video_info = self._get_video_metadata(video_url)
            if not video_info:
                print("영상 메타데이터를 가져오지 못했습니다. 다운로드를 계속할 수 없습니다.")
                return None

            video_id = video_info['video_id']
            uploader_name = video_info['uploader'].replace('@', '') if video_info['uploader'] else "Unknown_Account"
            duration = video_info['duration']

            # Determine video type (short_form or long_form) based on duration
            video_type_folder = "short_form"
            if duration is not None and duration > 60: # Assume > 60 seconds is long form (TikTok max is around 3 mins)
                video_type_folder = "long_form"
            
            # Construct base directory for this video's files
            # downloads/{account_name}/{video_type}/
            base_output_dir = self.download_dir / uploader_name / video_type_folder
            base_output_dir.mkdir(parents=True, exist_ok=True)

            # Construct output template for yt-dlp
            output_template = str(base_output_dir / "%(id)s.%(ext)s")
            
            command = [
                "yt-dlp",
                video_url,
                "-o", output_template,
                "--no-playlist",
                "--restrict-filenames",
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            ]
            
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
            download_path = None # This will be the actual downloaded path

            for line in iter(process.stdout.readline, ''):
                self._check_stop_event() # 중지 신호 확인
                print(f"[yt-dlp] {line.strip()}") # 모든 yt-dlp 출력을 로그로
                if "Destination:" in line and download_path is None: # Only set if not already found
                    download_path = line.split("Destination:")[-1].strip()
                elif "downloaded" in line.lower() and download_path is None: # general "downloaded" pattern
                    match = re.search(r'downloaded "(.*?)"', line)
                    if match:
                        download_path = match.group(1).strip()
            
            stderr_output = process.stderr.read()

            process.stdout.close()
            process.stderr.close() # Close stderr pipe too
            process.wait() # 프로세스 종료 대기

            if self.stop_event.is_set():
                return None

            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, command, stderr=stderr_output)

            # Validate download_path or construct it based on video_info
            if not download_path or not os.path.exists(download_path):
                # Fallback: Construct path assuming common video formats
                # This is a bit of a guess, better to rely on yt-dlp output
                possible_paths = [
                    base_output_dir / f"{video_id}.mp4",
                    base_output_dir / f"{video_id}.webm",
                    base_output_dir / f"{video_id}.mkv"
                ]
                for p in possible_paths:
                    if os.path.exists(p):
                        download_path = str(p)
                        break
                
                if not download_path or not os.path.exists(download_path):
                    print(f"yt-dlp 다운로드 실패 또는 경로를 찾을 수 없음: {stderr_output}")
                    return None
            
            # Pass full metadata and actual downloaded path to save_transcript
            video_info['downloaded_path'] = download_path
            return video_info # Return video_info including downloaded_path
        
        except InterruptedError:
            if 'process' in locals() and process.poll() is None:
                process.terminate()
                process.wait()
            print("작업이 중지되었습니다.")
            return None
        except subprocess.CalledProcessError as e:
            print(f"yt-dlp 실행 오류: {e.stderr}")
            return None
        except Exception as e:
            print(f"다운로드 중 예상치 못한 오류 발생: {e}")
            return None

    def download_all_videos_from_profile_url(self, profile_url):
        """계정 URL에서 모든 영상 다운로드 (yt-dlp 사용)"""
        self._check_stop_event()
        try:
            profile_name = profile_url.split('/')[-1].split('?')[0].replace('@', '')
            output_dir = self.download_dir / profile_name
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_template = str(output_dir / "%(id)s.%(ext)s")
            archive_file = str(output_dir / f"{profile_name}_archive.txt") # 중복 제외를 위한 아카이브 파일 경로

            command = [
                "yt-dlp",
                profile_url,
                "-o", output_template,
                "--yes-playlist",
                "--restrict-filenames",
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--no-warnings",
                "--download-archive", archive_file, # 아카이브 파일 지정
            ]
            
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
            downloaded_video_paths = []

            for line in iter(process.stdout.readline, ''):
                self._check_stop_event() # 중지 신호 확인
                print(f"[yt-dlp] {line.strip()}") # 모든 yt-dlp 출력을 로그로
                if "Destination:" in line:
                    path_match = re.search(r'Destination: (.*?\\.mp4|.*?\\.webm|.*?\\.mkv)', line)
                    if path_match:
                        download_path = path_match.group(1).strip()
                        if os.path.exists(download_path) and download_path not in downloaded_video_paths: # Check for existence and uniqueness
                            downloaded_video_paths.append(download_path)
                            print(f"[yt-dlp] 다운로드됨: {download_path}")
                elif "downloaded" in line.lower() and (".mp4" in line.lower() or ".webm" in line.lower() or ".mkv" in line.lower()):
                    match = re.search(r'downloaded "(.*?)"', line)
                    if match:
                        download_path = match.group(1).strip()
                        if os.path.exists(download_path) and download_path not in downloaded_video_paths: # Check for existence and uniqueness
                            downloaded_video_paths.append(download_path)
            
            # Read stderr after stdout is exhausted and process has finished
            stderr_output = process.stderr.read()

            process.stdout.close()
            process.stderr.close() # Close stderr pipe too
            process.wait()

            if self.stop_event.is_set():
                # Process terminated by stop event, handle clean exit
                return []

            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, command, stderr=stderr_output)

            return downloaded_video_paths

        except InterruptedError:
            if 'process' in locals() and process.poll() is None:
                process.terminate()
                process.wait()
            print("작업이 중지되었습니다.")
            return []
        except subprocess.CalledProcessError as e:
            print(f"yt-dlp 실행 오류 (계정): {stderr_output}") # Use the collected stderr
            return []
        except Exception as e:
            print(f"계정 영상 다운로드 중 예상치 못한 오류 발생: {e}")
            return []

    def extract_audio(self, video_path):
        """영상에서 오디오 추출""" 
        self._check_stop_event()
        try:
            audio_path = str(Path(video_path).with_suffix('.mp3'))
            # moviepy는 내부적으로 ffmpeg를 subprocess로 호출합니다.
            # moviepy에서 직접 subprocess를 제어하기 어렵기 때문에, 여기서는 중지 이벤트만 체크하고
            # moviepy의 write_audiofile이 블로킹될 경우 스레드 종료 신호에 반응하지 않을 수 있습니다.
            # 더 완벽한 중지 제어를 위해서는 moviepy 대신 ffmpeg 명령어를 직접 Popen으로 호출해야 합니다.
            
            # moviepy 사용 부분을 주석 처리하고 ffmpeg 직접 사용
            video = VideoFileClip(video_path)
            video.audio.write_audiofile(audio_path) # 이 부분이 블로킹될 수 있음
            video.close()
            
            # ffmpeg를 직접 사용하여 오디오 추출
            command = [
                "ffmpeg", "-i", video_path, "-vn", "-acodec", "mp3", 
                "-ab", "128k", "-ar", "44100", "-y", audio_path
            ]
            
            process = subprocess.run(command, capture_output=True, text=True, check=True)
            return audio_path
        except InterruptedError:
            print("오디오 추출 작업이 중지되었습니다.")
            return None
        except Exception as e:
            print(f"오디오 추출 중 오류 발생: {e}")
            return None

    def generate_transcript(self, audio_path):
        """오디오를 텍스트로 변환"""
        self._check_stop_event()
        try:
            print(f"[DEBUG] 대본 생성을 위해 오디오 경로 확인: {audio_path}") # 디버그 출력
            
            result = self.model.transcribe(audio_path) # 이 부분도 블로킹될 수 있음
            transcript_text = result["text"]
            
            print(f"[DEBUG] Whisper 대본 생성 완료. 텍스트 길이: {len(transcript_text) if transcript_text else 0}, 시작 부분: \"{transcript_text[:50]}...\"") # 디버그 출력
            return transcript_text
        except InterruptedError:
            print("대본 생성 작업이 중지되었습니다.")
            return None
        except Exception as e:
            print(f"대본 생성 중 오류 발생: {e}")
            return None

    def save_transcript(self, video_info, whisper_result):
        """대본 저장"""
        self._check_stop_event()
        try:
            video_id = video_info['video_id']
            video_title = video_info['video_title']
            uploader_name = video_info['uploader'].replace('@', '') if video_info['uploader'] else "Unknown_Account"
            
            # Determine transcript output directory: downloads/{account_name}/video_scripts/
            transcript_output_dir = self.download_dir / uploader_name / "video_scripts"
            transcript_output_dir.mkdir(parents=True, exist_ok=True) # 디렉토리가 없으면 생성

            # 간소화된 출력 내용
            output = {
                'video_title': video_title,
                'transcript_text': whisper_result["text"]
            }
            
            json_filename = transcript_output_dir / f"{video_id}_transcript.json"
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"대본이 다음 위치에 저장되었습니다: {json_filename}")

            # Markdown 파일로도 내보내기 (pass correct metadata, ensuring video_title is used)
            markdown_success = self.export_transcript_to_markdown(
                video_id,
                output['transcript_text'],
                transcript_output_dir,
                video_title # Pass the correct video_title here
            )

            if markdown_success:
                print("[DEBUG] Markdown 대본 내보내기 성공.")
                print("[DEBUG_SAVE_TRANSCRIPT] 대본 저장 및 마크다운 내보내기 성공.") # 디버그 출력 추가
                return True
            else:
                print("[DEBUG] Markdown 대본 내보내기 실패.")
                print("[DEBUG_SAVE_TRANSCRIPT] 대본 저장 또는 마크다운 내보내기 실패.") # 디버그 출력 추가
                return False

        except InterruptedError:
            print("대본 저장 작업이 중지되었습니다.")
            print("[DEBUG_SAVE_TRANSCRIPT] 대본 저장 작업 중지.") # 디버그 출력 추가
            return False
        except Exception as e:
            print(f"대본 저장 중 오류 발생: {e}")
            print(f"[DEBUG_SAVE_TRANSCRIPT] 대본 저장 중 예외 발생: {e}") # 디버그 출력 추가
            return False

    def export_transcript_to_markdown(self, video_id, transcript_text, output_dir, video_title):
        """
        대본을 Markdown 파일로 내보내어 블로그 게시물 작성을 돕습니다.
        요약문과 추천 상품 섹션을 포함합니다.
        """
        try:
            print(f"[DEBUG] export_transcript_to_markdown 호출됨. video_id: {video_id}, 대본 텍스트 길이: {len(transcript_text) if transcript_text else 0}") # 디버그 출력
            markdown_filename = output_dir / f"{video_id}.md"

            # 대본 요약 (간단한 추출 기반 요약)
            sentences = transcript_text.split('.')
            summary_sentences = []
            for i, sentence in enumerate(sentences):
                if i < 3: # 처음 3문장만 포함
                    trimmed_sentence = sentence.strip()
                    if trimmed_sentence: # 빈 문장이 아닌 경우에만 추가
                        summary_sentences.append(trimmed_sentence)
                else:
                    break
            summary = ". ".join(summary_sentences) + ("." if summary_sentences and not summary_sentences[-1].endswith('.') else "") # 마지막에 마침표 추가

            with open(markdown_filename, "w", encoding="utf-8") as f:
                f.write(f"# {video_title}\n\n")
                if summary:
                    f.write(f"**요약**: {summary}\n\n")
                f.write(f"{transcript_text}\n\n")
                f.write("## 추천 상품\n\n")
                f.write("<!-- 여기에 쿠팡 파트너스 상품 정보 및 링크를 추가하세요 -->\n")
            print(f"Markdown 대본이 다음 위치에 저장되었습니다: {markdown_filename}")
            return True
        except Exception as e:
            print(f"Markdown 대본 내보내기 중 오류 발생: {e}")
            return False

    def analyze_video_content(self, video_info, whisper_result):
        """
        영상 대본을 분석하여 태그 및 콘텐츠 아이디어를 생성합니다.
        (초기 버전: 간단한 키워드 추출)
        """
        suggested_tags = []
        content_ideas = [] # 블로그 및 새 영상 아이디어를 통합
        timestamped_summaries = [] # 세그먼트별 요약 및 타임스탬프

        if whisper_result and "text" in whisper_result:
            transcript = whisper_result["text"] # Extract transcript text
            segments = whisper_result.get("segments", []) # Get segments

            # 1. 키워드 추출 (기존 로직 유지)
            words = re.findall(r'\b\w+\b', transcript.lower()) # 영문과 숫자만으로 된 단어 추출
            korean_words = re.findall(r'[가-힣]+', transcript) # 한글 단어만 추출

            # 합치고 불용어 제거
            filtered_words = [word for word in (words + korean_words) if word not in self.KOREAN_STOPWORDS and len(word) > 1]
            
            # 단어 빈도 계산
            word_counts = collections.Counter(filtered_words)
            
            # 가장 흔한 단어 5개를 태그로 사용
            most_common_words = [word for word, count in word_counts.most_common(5)]
            suggested_tags = most_common_words

            # 2. 콘텐츠 아이디어 생성 (블로그 및 새 영상 아이디어 통합 및 간결화)
            video_title = video_info.get('video_title', '영상')
            main_tag = suggested_tags[0] if suggested_tags else '핵심 주제'
            
            # Gemini API를 사용하여 더 풍부한 콘텐츠 아이디어 생성
            if self.gemini_model:
                print(f"[DEBUG_API] Gemini 모델 사용 가능. Prompt 생성 중...") # 디버그 출력
                try:
                    prompt = f"다음 영상 대본의 핵심 내용과 키워드를 기반으로, 블로그 게시물 아이디어와 새로운 영상 제작 아이디어를 5가지씩 제안해주세요. 각 아이디어는 간결하게 한 문장으로 작성하고, 해시태그 형식(#블로그, #새영상)으로 시작해주세요.\n\n영상 제목: {video_info.get('video_title', '제목 없음')}\n대본 내용:\n{transcript[:2000]}..."
                    
                    response = self.gemini_model.generate_content(prompt)
                    
                    if response.candidates:
                        gemini_ideas_text = response.candidates[0].content.parts[0].text
                        # Gemini가 생성한 아이디어를 파싱하여 추가
                        for line in gemini_ideas_text.split('\n'):
                            stripped_line = line.strip()
                            if stripped_line and (stripped_line.startswith('#블로그') or stripped_line.startswith('#새영상')):
                                content_ideas.append(stripped_line)
                            elif stripped_line: # 해시태그 없는 경우도 일단 추가 (파싱 로직 개선 가능)
                                content_ideas.append(stripped_line)
                        print(f"[DEBUG_API] Gemini API 호출 성공. 생성된 아이디어 수: {len(content_ideas)}") # 디버그 출력
                    else:
                        print(f"[DEBUG_API] Gemini API 응답에 후보가 없습니다.") # 디버그 출력
                    self.gemini_model.count_tokens(prompt) # 토큰 카운트 (API 비용 확인용)

                except Exception as e:
                    print(f"[Gemini API 오류]: 콘텐츠 아이디어 생성 실패: {e}")
                    # Fallback to simple ideas if Gemini fails
                    content_ideas.append(f"#블로그: '{video_title}' 핵심 {main_tag} 심층 분석")
                    content_ideas.append(f"#새영상: '{video_title}'에서 다룬 {main_tag} 활용 아이디어")
                    content_ideas.append(f"#Q&A: '{video_title}' 관련 시청자 질문 답변")
            else:
                print("[DEBUG_API] Gemini 모델 초기화되지 않음. 기본 아이디어 생성.") # 디버그 출력
                # Gemini 모델이 초기화되지 않은 경우 (API 키 없음), 기존 로직 유지
                content_ideas.append(f"#블로그: '{video_title}' 핵심 {main_tag} 심층 분석")
                content_ideas.append(f"#새영상: '{video_title}'에서 다룬 {main_tag} 활용 아이디어")
                content_ideas.append(f"#Q&A: '{video_title}' 관련 시청자 질문 답변")

            # 3. 세그먼트별 요약 및 타임스탬프 추출
            if segments:
                for segment in segments:
                    timestamped_summaries.append({
                        'start': segment['start'],
                        'end': segment['end'],
                        'text': segment['text'].strip()
                    })
            else: # Fallback if no segments are present (shouldn't happen with Whisper result, but for safety)
                sentences = re.split(r'(?<=[.!?]) +', transcript.strip()) # 문장 분리
                mock_timestamp = 0
                for i, sentence in enumerate(sentences):
                    if not sentence.strip():
                        continue
                    timestamped_summaries.append({
                        'start': mock_timestamp,
                        'end': mock_timestamp + len(sentence) * 0.1, # 임의의 시간
                        'text': sentence.strip()
                    })
                    mock_timestamp += len(sentence) * 0.1 + 1 # 다음 문장 시작 시간

        return {
            'suggested_tags': suggested_tags,
            'content_ideas': content_ideas, # 통합된 콘텐츠 아이디어
            'timestamped_summaries': timestamped_summaries # 세그먼트별 요약 및 타임스탬프
        }

    def save_analysis_results(self, video_info, analysis_results):
        """
        분석 결과를 JSON 파일로 저장합니다.
        """
        self._check_stop_event()
        try:
            video_id = video_info['video_id']
            uploader_name = video_info['uploader'].replace('@', '') if video_info['uploader'] else "Unknown_Account"
            
            # Determine analysis output directory: downloads/{account_name}/video_analysis/
            analysis_output_dir = self.download_dir / uploader_name / "video_analysis"
            analysis_output_dir.mkdir(parents=True, exist_ok=True) # 디렉토리가 없으면 생성

            json_filename = analysis_output_dir / f"{video_id}_analysis.json"
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(analysis_results, f, ensure_ascii=False, indent=2)
            print(f"분석 결과가 다음 위치에 저장되었습니다: {json_filename}")
            return True
        except InterruptedError:
            print("분석 결과 저장 작업이 중지되었습니다.")
            return False
        except Exception as e:
            print(f"분석 결과 저장 중 오류 발생: {e}")
            return False

    def get_previous_analyses(self):
        """
        이전에 분석된 영상들의 목록과 해당 분석 결과 파일 경로를 가져옵니다.
        """
        previous_analyses = []
        analysis_root_dir = self.download_dir # downloads 폴더가 기준

        for uploader_dir in analysis_root_dir.iterdir():
            if uploader_dir.is_dir():
                analysis_dir = uploader_dir / "video_analysis"
                if analysis_dir.is_dir():
                    for analysis_file in analysis_dir.glob("*_analysis.json"):
                        try:
                            with open(analysis_file, "r", encoding="utf-8") as f:
                                analysis_data = json.load(f)
                            
                            # Assuming video_info is also saved with analysis or can be inferred from filename
                            video_id = analysis_file.stem.replace("_analysis", "")
                            # For simplicity, we might not have all video_info here, just analysis results
                            # In a real app, video_info would be part of the analysis_results or a separate file

                            # To get video_title from transcript json (if available)
                            transcript_file = uploader_dir / "video_scripts" / f"{video_id}_transcript.json"
                            video_title = "Unknown Title"
                            if transcript_file.exists():
                                try:
                                    with open(transcript_file, "r", encoding="utf-8") as tf:
                                        transcript_data = json.load(tf)
                                        video_title = transcript_data.get('video_title', video_title)
                                except Exception as te:
                                    print(f"대본 파일 읽기 오류 {transcript_file}: {te}")
                            
                            previous_analyses.append({
                                'video_id': video_id,
                                'video_title': video_title,
                                'uploader': uploader_dir.name, # Uploader name is the directory name
                                'analysis_file_path': str(analysis_file)
                            })
                        except Exception as e:
                            print(f"분석 파일 읽기 오류 {analysis_file}: {e}")
        return previous_analyses

    def generate_product_description_from_analysis(self, transcript_content: str, suggested_tags: list[str], content_ideas: list[str], timestamped_summaries: list[dict]) -> str:
        """영상 분석 결과(대본, 태그, 아이디어, 요약)를 바탕으로 상품 설명을 자동으로 생성합니다."""
        if not self.gemini_model:
            print("[ERROR] Gemini 모델이 초기화되지 않았습니다. 상품 설명을 생성할 수 없습니다.")
            return ""

        self._check_stop_event()
        try:
            # 분석 데이터를 바탕으로 상품 설명 프롬프트 구성
            analysis_summary_parts = []
            if suggested_tags: analysis_summary_parts.append(f"주요 태그: {', '.join(suggested_tags)}.")
            if content_ideas: analysis_summary_parts.append(f"콘텐츠 아이디어: {'; '.join(content_ideas)}.")
            if timestamped_summaries:
                summary_texts = [s['text'] for s in timestamped_summaries]
                analysis_summary_parts.append(f"영상 핵심 요약: {'. '.join(summary_texts)}.")
            
            analysis_summary = " ".join(analysis_summary_parts)

            prompt = f"""
당신은 마케팅 전문가이며, 영상 분석 결과를 바탕으로 제품에 대한 매력적인 설명을 작성하는 데 능숙합니다.
아래에 제공된 영상 대본과 분석 데이터를 참고하여, 이 영상에서 소개될 만한 가상의 제품에 대한 설명을 500자 내외로 작성해주세요.
이 설명은 쿠팡 파트너스 블로그에 사용될 예정이므로, 제품의 주요 특징, 장점, 대상 고객, 그리고 이 제품이 왜 좋은지에 대한 설득력 있는 내용을 포함해야 합니다.

**영상 대본 내용:**
{transcript_content[:8000]}

**영상 분석 요약:**
{analysis_summary}

**요청하는 상품 설명:**
간결하고 매력적이며 설득력 있는 한국어로 제품 설명을 작성해주세요. 이 설명은 실제 쿠팡 상품 페이지의 설명을 대체할 수 있을 정도로 구체적이고 유용해야 합니다.
"""
            print(f"[DEBUG_API] Gemini 상품 설명 생성 프롬프트: {prompt[:500]}...")

            response = self.gemini_model.generate_content(prompt)
            
            if response.candidates:
                generated_description = response.candidates[0].content.parts[0].text
                print(f"[DEBUG_API] Gemini 상품 설명 생성 결과: {generated_description[:500]}...")
                return generated_description
            else:
                print("[ERROR] Gemini API에서 상품 설명을 생성하지 못했습니다.")
                return ""
        except InterruptedError:
            print("[INFO] 상품 설명 생성 작업이 중지되었습니다.")
            return ""
        except Exception as e:
            print(f"[ERROR] 상품 설명 생성 중 오류 발생: {e}")
            return ""

    def generate_product_script(self, product_features: str, target_audience: str = "", video_purpose: str = "구매 유도") -> str:
        """제품 특징, 대상 고객, 영상 목적을 바탕으로 제품 영상 스크립트/후크를 생성합니다."""
        self._check_stop_event()
        if not self.gemini_model:
            print("[ERROR] Gemini 모델이 초기화되지 않았습니다. 스크립트 생성 불가.")
            return "Gemini 모델이 준비되지 않았습니다. GOOGLE_API_KEY를 확인해주세요."

        prompt_parts = [
            "당신은 제품 영상 스크립트 및 후크 생성 전문 AI입니다. 다음 정보를 바탕으로 짧고 강력한 제품 영상 스크립트 또는 후크를 생성해주세요.\n",
            f"제품 특징 및 장점: {product_features}\n",
        ]
        if target_audience: # 대상 고객이 입력된 경우에만 추가
            prompt_parts.append(f"대상 고객: {target_audience}\n")
        prompt_parts.append(f"영상 목적: {video_purpose}\n\n")
        prompt_parts.append("생성될 내용은 다음과 같은 요소를 포함해야 합니다:\n")
        prompt_parts.append("- 시청자의 시선을 사로잡는 강력한 후크 (초반 5-10초)\n")
        prompt_parts.append("- 제품의 핵심 특징과 장점을 간결하고 명확하게 전달\n")
        prompt_parts.append("- 영상 목적에 맞는 구체적인 콜투액션 (CTA) 제안 (예: '지금 구매하세요!', '더 알아보기', '구독하세요!')\n")
        prompt_parts.append("- (선택 사항) 영상 끝맺음 멘트\n\n")
        prompt_parts.append("간결하고 매력적인 스크립트 또는 후크 초안을 작성해주세요. 길이는 150단어 내외로 해주세요.\n")

        full_prompt = "".join(prompt_parts)
        print(f"[DEBUG_API] Gemini 제품 스크립트 생성 프롬프트: {full_prompt[:500]}...") # 디버그 출력

        try:
            response = self.gemini_model.generate_content(full_prompt, generation_config=self.generation_config)
            if response.candidates:
                generated_text = response.candidates[0].content.parts[0].text
                print(f"[DEBUG_API] Gemini 제품 스크립트 생성 결과: {generated_text[:500]}...") # 디버그 출력
                return generated_text
            else:
                print("[ERROR] Gemini 제품 스크립트 생성 실패: 후보 없음.")
                return "스크립트 생성에 실패했습니다. 다시 시도해주세요."
        except Exception as e:
            print(f"[ERROR] Gemini 제품 스크립트 생성 중 오류 발생: {e}")
            return f"스크립트 생성 중 오류가 발생했습니다: {e}"

    def generate_coupang_blog_draft(self, product_url: str, product_description: str, transcript_content: str, manual_image_url: str = None) -> str:
        """
        Gemini API를 사용하여 쿠팡 파트너스 블로그 초안을 생성합니다.
        영상 대본 내용을 추가하여 블로그 초안의 관련성을 높입니다.
        """
        if not self.gemini_model:
            print("[ERROR] Gemini 모델이 초기화되지 않았습니다. 쿠팡 블로그 초안을 생성할 수 없습니다.")
            return ""

        self._check_stop_event()
        try:
            # 디버그: 전달받은 product_url 확인
            print(f"[DEBUG_API] 쿠팡 블로그 초안 생성 시작 - 전달받은 product_url: {product_url}")
            
            image_html = ""
            if manual_image_url: # 수동으로 입력된 이미지 URL이 있다면 그것을 사용
                image_url = manual_image_url
                image_html = f"<p><img src=\"{image_url}\" alt=\"상품 이미지\" style=\"max-width: 100%; height: auto; display: block; margin: 0 auto;\"></p>\n"
                print(f"[DEBUG_API] 수동 이미지 URL 사용: {image_url}")
            else: # 수동 URL이 없으면 API를 통해 가져오기 시도
                product_info = self._get_coupang_product_info_from_api(product_url=product_url)
                if product_info and product_info.get("productImage"):
                    image_url = product_info["productImage"]
                    image_html = f"<p><img src=\"{image_url}\" alt=\"상품 이미지\" style=\"max-width: 100%; height: auto; display: block; margin: 0 auto;\"></p>\n"
                    print(f"[DEBUG_API] 쿠팡 상품 이미지 URL 가져옴: {image_url}")
                else:
                    print("[DEBUG_API] 쿠팡 상품 이미지를 가져오지 못했습니다. (API 또는 ID 없음)")

            # 쿠팡 블로그 초안 생성을 위한 프롬프트 구성
            prompt = f"""
당신은 마케팅 전문가이자 카피라이터입니다. 다음 정보를 바탕으로 쿠팡 파트너스 블로그 게시물 초안을 HTML 형식으로 작성해주세요.

**중요: 반드시 다음 쿠팡 파트너스 상품 URL만 사용하세요. 다른 링크나 예시 링크를 사용하지 마세요.**
**쿠팡 파트너스 상품 URL:** {product_url}
**상품 설명:** {product_description}

**영상 대본 내용 (참고용):**
{transcript_content[:8000]}

**상품 이미지 (삽입 필요 시):**
{image_html}

**블로그 게시물에 포함되어야 할 내용:**
1.  **제목**: 검색 엔진 최적화(SEO)를 고려한 매력적이고 클릭을 유도하는 제목 (상품명과 관련된 키워드 포함)
2.  **도입부**: 상품에 대한 흥미를 유발하고, 상품이 해결해 줄 수 있는 문제점이나 제공할 수 있는 가치에 대해 언급
3.  **상품 상세 설명 (본론)**:
    *   상품 설명에서 제공된 특징과 장점을 중심으로 구체적으로 설명
    *   만약 영상 대본 내용이 상품과 관련 있다면, 대본 내용에서 언급된 상품의 장점이나 사용 사례를 자연스럽게 통합
    *   사용자의 궁금증을 해소하고 구매 욕구를 자극할 수 있는 내용 포함
    *   단락별로 소제목을 사용하여 가독성을 높일 것
4.  **이미지 삽입**: 제공된 '상품 이미지' HTML 태그가 있다면 본론의 적절한 위치에 삽입하여 시각적 효과를 높여주세요. 없으면 생략합니다.
5.  **쿠팡 파트너스 링크 삽입**: 블로그 게시물 내용 중 2-3곳에 상품과 관련된 문구와 함께 다음 형식으로 쿠팡 파트너스 링크를 **직접 삽입**해주세요: `<a href="{product_url}">상품 구매하기</a>`. 또한, 게시물 하단에는 반드시 "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다." 문구를 **명확하게 포함**해야 합니다.
6.  **결론**: 상품의 핵심적인 가치를 다시 한번 강조하고, 구매를 망설이는 독자에게 최종적인 구매 결정을 내리도록 유도
7.  **추천 태그**: 블로그 게시물에 사용할 관련 해시태그 (5개 이상, SEO 고려) - HTML 형식에 맞게 처리

**주의사항:**
*   블로그 게시물은 자연스럽고 설득력 있는 한국어로 작성해야 합니다.
*   과도한 반복이나 스팸성 내용은 피해주세요.
*   상품 설명에 없는 내용은 임의로 추가하지 마세요.
*   영상 대본 내용은 참고용이며, 상품 설명이 우선시됩니다. 대본 내용 중 상품과 직접 관련 없는 부분은 무시해도 좋습니다.
*   생성되는 전체 응답은 HTML 형식이어야 합니다. `<h1>`, `<h2>`, `<p>`, `<ul>`, `<li>`, `<strong>`, `<em>`, `<a>`, `<img>` 등의 HTML 태그를 적절히 사용하여 웹페이지에 바로 게시할 수 있는 형태로 만들어주세요.
*   **가장 중요한 점: 반드시 위에서 제공된 쿠팡 파트너스 상품 URL({product_url})만 사용하세요. 다른 링크나 예시 링크를 절대 사용하지 마세요.**

최대한 자세하고 설득력 있는 블로그 게시물 초안을 작성해주세요.
"""
            response = self.gemini_model.generate_content(prompt)
            
            if response.candidates:
                generated_blog_draft = response.candidates[0].content.parts[0].text
                return generated_blog_draft
            else:
                print("[ERROR] Gemini API에서 블로그 초안을 생성하지 못했습니다.")
                return ""
        except InterruptedError:
            print("[INFO] 쿠팡 파트너스 블로그 초안 생성 작업이 중지되었습니다.")
            return ""
        except Exception as e:
            print(f"[ERROR] 쿠팡 파트너스 블로그 초안 생성 중 오류 발생: {e}")
            return ""

    def generate_platform_optimized_content(self, platform_type: str, product_url: str, product_description: str, transcript_content: str) -> str:
        """
        주어진 플랫폼 유형에 맞춰 최적화된 콘텐츠(인스타그램 캡션, 유튜브 설명 등)를 Gemini API로 생성합니다.
        """
        if not self.gemini_model:
            print("[ERROR] Gemini 모델이 초기화되지 않았습니다. 플랫폼 최적화 콘텐츠를 생성할 수 없습니다.")
            return ""

        self._check_stop_event()
        # 디버그: 전달받은 product_url 확인
        print(f"[DEBUG_API] {platform_type} 콘텐츠 생성 시작 - 전달받은 product_url: {product_url}")
        
        prompt = ""
        try:
            if platform_type == "instagram":
                prompt = f"""
당신은 인스타그램 마케팅 전문가입니다. 아래 상품 설명과 영상 대본을 참고하여 인스타그램 게시물 캡션을 2200자 이내로 작성하고, 관련 해시태그 10개를 추천해주세요. 이 캡션은 사용자의 참여를 유도하고, 제품 구매로 이어질 수 있도록 매력적이어야 합니다.

**중요: 반드시 다음 쿠팡 파트너스 상품 URL만 사용하세요. 다른 링크나 예시 링크를 사용하지 마세요.**
상품 구매 링크: {product_url}

**상품 설명:**
{product_description}

**영상 대본 내용 (참고용):**
{transcript_content[:8000]}

**인스타그램 캡션 작성 규칙:**
- 2200자 이내로 작성
- 이모지 적절히 사용
- 핵심 메시지는 초반에 배치
- 사용자에게 질문을 던지거나 참여를 유도하는 문구 포함
- 마지막에는 [상품 구매하기]({product_url}) 링크 삽입 유도 (링크는 실제 게시 시 변경될 수 있음을 안내)
- 맨 아래에 이 포스팅이 쿠팡 파트너스 활동의 일환이라는 면책 조항을 포함해주세요. (예: "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.")
- 관련 해시태그 10개 포함 (예: #상품명 #추천템 #인생템)
- **가장 중요한 점: 반드시 위에서 제공된 쿠팡 파트너스 상품 URL({product_url})만 사용하세요. 다른 링크나 예시 링크를 절대 사용하지 마세요.**

인스타그램 캡션을 작성해주세요:
"""
            elif platform_type == "youtube_description":
                prompt = f"""
당신은 유튜브 콘텐츠 전문가입니다. 아래 상품 설명과 영상 대본을 참고하여 유튜브 영상 설명을 작성해주세요. 이 설명은 검색 엔진 최적화(SEO)를 고려하여 관련 키워드를 포함하고, 시청자가 제품에 대해 더 자세히 알아보고 구매할 수 있도록 유도해야 합니다.

**중요: 반드시 다음 쿠팡 파트너스 상품 URL만 사용하세요. 다른 링크나 예시 링크를 사용하지 마세요.**
상품 구매 링크: {product_url}

**상품 설명:**
{product_description}

**영상 대본 내용 (참고용):**
{transcript_content[:8000]}

**유튜브 영상 설명 작성 규칙:**
- 영상의 내용을 요약하고, 제품의 핵심 특징과 장점을 강조
- 관련성 높은 키워드를 자연스럽게 포함 (SEO 최적화)
- 타임스탬프가 있다면 활용하여 영상 내 특정 구간 안내 (이번 요청에서는 불필요)
- [상품 구매하기]({product_url}) 링크를 명확하게 포함 (영상 설명 상단이나 중단에 배치)
- 영상 관련 추가 정보나 채널 소개 등도 포함 가능
- 마지막에는 이 포스팅이 쿠팡 파트너스 활동의 일환이라는 면책 조항을 포함해주세요. (예: "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.")
- 관련 해시태그 5~10개 포함
- **가장 중요한 점: 반드시 위에서 제공된 쿠팡 파트너스 상품 URL({product_url})만 사용하세요. 다른 링크나 예시 링크를 절대 사용하지 마세요.**

유튜브 영상 설명을 작성해주세요:
"""
            elif platform_type == "threads" or platform_type == "twitter":
                char_limit = 500 if platform_type == "threads" else 280
                prompt = f"""
당신은 소셜 미디어 전문가입니다. 아래 상품 설명과 영상 대본을 참고하여 {platform_type} 게시물 콘텐츠를 {char_limit}자 이내로 작성해주세요. 짧고 간결하면서도 시선을 사로잡는 내용이어야 하며, 제품에 대한 흥미를 유발하고 상품 구매로 이어질 수 있도록 유도해야 합니다.

**중요: 반드시 다음 쿠팡 파트너스 상품 URL만 사용하세요. 다른 링크나 예시 링크를 사용하지 마세요.**
상품 구매 링크: {product_url}

**상품 설명:**
{product_description}

**영상 대본 내용 (참고용):**
{transcript_content[:8000]}

**{platform_type} 게시물 작성 규칙:**
- {char_limit}자 이내로 간결하게 작성
- 강력한 후크로 시선 집중
- 제품의 핵심 가치 전달
- [상품 구매하기]({product_url}) 링크를 명확하게 포함
- 마지막에는 이 포스팅이 쿠팡 파트너스 활동의 일환이라는 면책 조항을 포함해주세요. (예: "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.")
- 관련 해시태그 3-5개 포함
- **가장 중요한 점: 반드시 위에서 제공된 쿠팡 파트너스 상품 URL({product_url})만 사용하세요. 다른 링크나 예시 링크를 절대 사용하지 마세요.**

{platform_type} 게시물을 작성해주세요:
"""
            else:
                print(f"[ERROR] 지원하지 않는 플랫폼 유형입니다: {platform_type}")
                return ""

            print(f"[DEBUG_API] Gemini {platform_type} 콘텐츠 생성 프롬프트: {prompt[:500]}...")

            response = self.gemini_model.generate_content(prompt)
            
            if response.candidates:
                generated_content = response.candidates[0].content.parts[0].text
                print(f"[DEBUG_API] Gemini {platform_type} 콘텐츠 생성 결과: {generated_content[:500]}...")
                return generated_content
            else:
                print(f"[ERROR] Gemini API에서 {platform_type} 콘텐츠를 생성하지 못했습니다.")
                return ""
        except InterruptedError:
            print(f"[INFO] {platform_type} 콘텐츠 생성 작업이 중지되었습니다.")
            return ""
        except Exception as e:
            print(f"[ERROR] {platform_type} 콘텐츠 생성 중 오류 발생: {e}")
            return ""

    def _generate_hmac(self, method, url, secret_key, access_key):
        path, *query = url.split("?")
        os.environ["TZ"] = "GMT+0"
        datetime_gmt = time.strftime('%y%m%d')+'T'+time.strftime('%H%M%S')+'Z'
        message = datetime_gmt + method + path + (query[0] if query else "")
        signature = hmac.new(bytes(secret_key, "utf-8"),
                            message.encode("utf-8"),
                            hashlib.sha256).hexdigest()

        return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"

    def _get_coupang_product_info_from_api(self, product_url: str = None, product_id: str = None):
        """쿠팡 파트너스 API를 통해 상품 정보를 가져옵니다."""
        if not self.coupang_access_key or not self.coupang_secret_key:
            print("쿠팡 파트너스 API 키가 설정되지 않아 상품 정보를 가져올 수 없습니다.")
            return None

        headers = {"Accept": "application/json"}
        DOMAIN = "https://api.coupang.com"

        if product_url:
            # 상품 URL에서 product_id를 추출
            match = re.search(r'itemId=(\d+)', product_url)
            if match:
                product_id = match.group(1)
            else:
                print(f"경고: 쿠팡 파트너스 URL에서 product ID를 찾을 수 없습니다: {product_url}")
                return None

        if not product_id:
            print("상품 ID가 제공되지 않았습니다.")
            return None

        # 특정 상품 조회 API 엔드포인트
        url_path = f"/v2/providers/seller_api/apis/api/v1/marketplace/vendoritems/{product_id}"
        request_url = DOMAIN + url_path
        
        authorization = self._generate_hmac("GET", url_path, self.coupang_secret_key, self.coupang_access_key)
        headers["Authorization"] = authorization

        try:
            response = requests.get(request_url, headers=headers)
            response.raise_for_status() # HTTP 오류 발생 시 예외 발생
            product_data = response.json()
            print(f"[DEBUG_API] 쿠팡 상품 정보 API 응답: {product_data}")
            
            if product_data and product_data.get("data"):
                return product_data["data"]
            else:
                print(f"쿠팡 API 응답에 상품 데이터가 없습니다: {product_data}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"쿠팡 API 호출 오류: {e}")
            return None
        except Exception as e:
            print(f"_get_coupang_product_info_from_api 중 예상치 못한 오류 발생: {e}")
            return None 

    def get_channel_videos_with_filters(self, channel_url, min_views=None, video_type=None, keywords=None):
        """채널에서 조건에 맞는 동영상 목록을 가져옵니다."""
        self._check_stop_event()
        try:
            print(f"[DEBUG] 채널 필터링 시작: {channel_url}")
            
            # yt-dlp를 사용하여 채널의 동영상 목록 가져오기
            command = [
                "yt-dlp",
                "--dump-json",
                "--flat-playlist",
                "--no-download",
                channel_url
            ]
            
            process = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
            videos_data = process.stdout.strip().split('\n')
            
            filtered_videos = []
            for video_data in videos_data:
                if not video_data.strip():
                    continue
                    
                try:
                    video_info = json.loads(video_data)
                    if self._matches_filter_criteria(video_info, min_views, video_type, keywords):
                        filtered_videos.append(video_info)
                except json.JSONDecodeError:
                    continue
            
            print(f"[DEBUG] 필터링 완료: {len(filtered_videos)}개 동영상 선택됨")
            return filtered_videos
            
        except subprocess.CalledProcessError as e:
            print(f"채널 정보 가져오기 오류: {e.stderr}")
            return []
        except Exception as e:
            print(f"채널 필터링 중 오류 발생: {e}")
            return []

    def _matches_filter_criteria(self, video_info, min_views=None, video_type=None, keywords=None):
        """동영상이 필터 조건에 맞는지 확인합니다."""
        try:
            # 조회수 필터링
            if min_views is not None:
                view_count = video_info.get('view_count', 0)
                if view_count < min_views:
                    return False
            
            # 동영상 유형 필터링 (숏폼/롱폼)
            if video_type is not None:
                duration = video_info.get('duration', 0)
                if video_type == "숏폼" and duration > 60:  # 60초 초과는 롱폼
                    return False
                elif video_type == "롱폼" and duration <= 60:  # 60초 이하는 숏폼
                    return False
            
            # 키워드 필터링
            if keywords:
                title = video_info.get('title', '').lower()
                description = video_info.get('description', '').lower()
                search_text = f"{title} {description}"
                
                keyword_list = [kw.strip().lower() for kw in keywords.split(',')]
                for keyword in keyword_list:
                    if keyword not in search_text:
                        return False
            
            return True
            
        except Exception as e:
            print(f"필터 조건 확인 중 오류: {e}")
            return False

    def download_filtered_videos(self, filtered_videos, output_dir=None):
        """필터링된 동영상들을 순차적으로 다운로드합니다."""
        self._check_stop_event()
        try:
            if not filtered_videos:
                print("다운로드할 동영상이 없습니다.")
                return []
            
            downloaded_videos = []
            total_videos = len(filtered_videos)
            
            for i, video_info in enumerate(filtered_videos, 1):
                if self.stop_event.is_set():
                    break
                
                try:
                    video_url = video_info.get('webpage_url') or video_info.get('url')
                    if not video_url:
                        continue
                    
                    print(f"[{i}/{total_videos}] 다운로드 중: {video_info.get('title', 'Unknown')}")
                    
                    # 개별 동영상 다운로드
                    downloaded_info = self.download_video_from_url(video_url)
                    if downloaded_info:
                        downloaded_videos.append(downloaded_info)
                        print(f"✅ 다운로드 완료: {downloaded_info.get('video_title', 'Unknown')}")
                    else:
                        print(f"❌ 다운로드 실패: {video_info.get('title', 'Unknown')}")
                
                except Exception as e:
                    print(f"동영상 다운로드 중 오류: {e}")
                    continue
            
            print(f"총 {len(downloaded_videos)}개 동영상 다운로드 완료")
            return downloaded_videos
            
        except Exception as e:
            print(f"필터링된 동영상 다운로드 중 오류: {e}")
            return []

    def process_channel_with_filters(self, channel_url, min_views=None, video_type=None, keywords=None):
        """채널 URL을 받아서 필터링 조건에 맞는 동영상들을 처리합니다."""
        self._check_stop_event()
        try:
            print(f"채널 처리 시작: {channel_url}")
            print(f"필터 조건 - 최소 조회수: {min_views}, 유형: {video_type}, 키워드: {keywords}")
            
            # 1단계: 필터링된 동영상 목록 가져오기
            filtered_videos = self.get_channel_videos_with_filters(channel_url, min_views, video_type, keywords)
            
            if not filtered_videos:
                print("조건에 맞는 동영상이 없습니다.")
                return []
            
            # 2단계: 필터링된 동영상들 다운로드
            downloaded_videos = self.download_filtered_videos(filtered_videos)
            
            # 3단계: 각 동영상에 대해 분석 수행 (선택사항)
            for video_info in downloaded_videos:
                if self.stop_event.is_set():
                    break
                
                try:
                    # 오디오 추출 및 대본 생성 (현재는 더미 데이터)
                    video_path = video_info.get('downloaded_path')
                    if video_path and os.path.exists(video_path):
                        audio_path = self.extract_audio(video_path)
                        if audio_path:
                            transcript = self.generate_transcript(audio_path)
                            if transcript:
                                # 대본 저장
                                self.save_transcript(video_info, {"text": transcript})
                                
                                # 콘텐츠 분석
                                analysis_results = self.analyze_video_content(video_info, {"text": transcript})
                                self.save_analysis_results(video_info, analysis_results)
                
                except Exception as e:
                    print(f"동영상 분석 중 오류: {e}")
                    continue
            
            return downloaded_videos
            
        except Exception as e:
            print(f"채널 처리 중 오류: {e}")
            return []

    # 숏츠 제작 지원 메서드들
    def generate_shorts_script(self, transcript_content: str, video_length: str, platform: str, content_type: str) -> str:
        """숏츠 전용 스크립트를 생성합니다."""
        if not self.gemini_model:
            return "Gemini API가 설정되지 않았습니다."
        
        try:
            prompt = f"""
다음은 원본 영상의 대본입니다. 이를 바탕으로 {video_length} 길이의 {platform} 숏츠용 스크립트를 생성해주세요.

**원본 대본:**
{transcript_content}

**요구사항:**
- 길이: {video_length}
- 플랫폼: {platform}
- 콘텐츠 유형: {content_type}
- 숏츠에 최적화된 빠른 템포와 임팩트 있는 문장 구성
- 시청자의 관심을 사로잡는 도입부
- 명확한 핵심 메시지 전달
- 강력한 마무리 (CTA 포함)

**출력 형식:**
1. 전체 스크립트 (말하는 대로 작성)
2. 주요 포인트별 시간 배분
3. 시각적 요소 제안 (자막, 이모지, 효과 등)

숏츠 스크립트를 생성해주세요.
"""
            
            response = self.gemini_model.generate_content(prompt)
            return response.text if response.text else "스크립트 생성에 실패했습니다."
            
        except Exception as e:
            return f"스크립트 생성 중 오류 발생: {e}"

    def generate_shorts_hook(self, transcript_content: str, platform: str, content_type: str) -> str:
        """숏츠용 후크(Hook)를 생성합니다."""
        if not self.gemini_model:
            return "Gemini API가 설정되지 않았습니다."
        
        try:
            prompt = f"""
다음은 원본 영상의 대본입니다. 이를 바탕으로 {platform} 숏츠용 후크(Hook)를 생성해주세요.

**원본 대본:**
{transcript_content}

**요구사항:**
- 플랫폼: {platform}
- 콘텐츠 유형: {content_type}
- 처음 3초를 사로잡는 강력한 후크
- 시청자가 끝까지 보게 만드는 임팩트
- 플랫폼별 특성에 맞는 후크 스타일

**출력 형식:**
1. 후크 문구 (3가지 버전)
2. 각 후크의 장점과 특징
3. 시각적 요소 제안 (자막 스타일, 이모지, 효과)
4. 후크 이후 이어질 내용 제안

후크를 생성해주세요.
"""
            
            response = self.gemini_model.generate_content(prompt)
            return response.text if response.text else "후크 생성에 실패했습니다."
            
        except Exception as e:
            return f"후크 생성 중 오류 발생: {e}"

    def generate_shorts_hashtags(self, transcript_content: str, platform: str, content_type: str) -> str:
        """숏츠용 최적화된 해시태그를 생성합니다."""
        if not self.gemini_model:
            return "Gemini API가 설정되지 않았습니다."
        
        try:
            prompt = f"""
다음은 원본 영상의 대본입니다. 이를 바탕으로 {platform} 숏츠용 최적화된 해시태그를 생성해주세요.

**원본 대본:**
{transcript_content}

**요구사항:**
- 플랫폼: {platform}
- 콘텐츠 유형: {content_type}
- 현재 트렌드에 맞는 인기 해시태그
- 플랫폼별 최적화 (TikTok, YouTube Shorts, Instagram Reels)
- 검색 최적화를 위한 관련 키워드
- 브랜드 해시태그 제안

**출력 형식:**
1. 핵심 해시태그 (5-7개)
2. 트렌드 해시태그 (3-5개)
3. 플랫폼별 특화 해시태그
4. 검색 최적화 키워드
5. 브랜드/개인 해시태그 제안
6. 해시태그 사용 팁

최적화된 해시태그를 생성해주세요.
"""
            
            response = self.gemini_model.generate_content(prompt)
            return response.text if response.text else "해시태그 생성에 실패했습니다."
            
        except Exception as e:
            return f"해시태그 생성 중 오류 발생: {e}"

    def generate_shorts_timeline(self, transcript_content: str, video_length: str, platform: str) -> str:
        """숏츠 편집용 타임라인을 생성합니다."""
        if not self.gemini_model:
            return "Gemini API가 설정되지 않았습니다."
        
        try:
            prompt = f"""
다음은 원본 영상의 대본입니다. 이를 바탕으로 {video_length} 길이의 {platform} 숏츠 편집 타임라인을 생성해주세요.

**원본 대본:**
{transcript_content}

**요구사항:**
- 길이: {video_length}
- 플랫폼: {platform}
- 숏츠에 최적화된 빠른 편집
- 시각적 임팩트를 위한 화면 전환 포인트
- 자막 타이밍 최적화
- 효과음/음악 제안

**출력 형식:**
1. 시간별 편집 가이드 (초 단위)
2. 화면 전환 포인트
3. 자막 표시 타이밍
4. 효과음/음악 제안
5. 시각적 효과 제안
6. 편집 소프트웨어별 팁

편집 타임라인을 생성해주세요.
"""
            
            response = self.gemini_model.generate_content(prompt)
            return response.text if response.text else "타임라인 생성에 실패했습니다."
            
        except Exception as e:
            return f"타임라인 생성 중 오류 발생: {e}"

    def generate_shorts_ab_test(self, transcript_content: str, platform: str, content_type: str) -> str:
        """숏츠 A/B 테스트 시나리오를 생성합니다."""
        if not self.gemini_model:
            return "Gemini API가 설정되지 않았습니다."
        
        try:
            prompt = f"""
다음은 원본 영상의 대본입니다. 이를 바탕으로 {platform} 숏츠용 A/B 테스트 시나리오를 생성해주세요.

**원본 대본:**
{transcript_content}

**요구사항:**
- 플랫폼: {platform}
- 콘텐츠 유형: {content_type}
- 다양한 후크 버전
- 다른 마무리 스타일
- 다양한 편집 스타일
- 성과 측정 지표 제안

**출력 형식:**
1. A/B 테스트 시나리오 (3-4개 버전)
2. 각 버전의 차이점과 특징
3. 예상 성과 지표
4. 테스트 기간 및 방법
5. 결과 분석 방법
6. 최적화 제안

A/B 테스트 시나리오를 생성해주세요.
"""
            
            response = self.gemini_model.generate_content(prompt)
            return response.text if response.text else "A/B 테스트 시나리오 생성에 실패했습니다."
            
        except Exception as e:
            return f"A/B 테스트 시나리오 생성 중 오류 발생: {e}" 