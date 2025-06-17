import sys
import threading
import re
import json
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QHBoxLayout,
    QProgressBar, QMessageBox, QFileDialog, QTextBrowser, QInputDialog, QListWidget, QListWidgetItem, QScrollArea, QTabWidget, QComboBox
)
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from api_handler import VideoProcessor
from pathlib import Path
import os
import platform
import webbrowser
import subprocess
from datetime import datetime

# 신호를 통해 스레드에서 UI 업데이트
class WorkerSignals(QObject):
    progress = pyqtSignal(int)
    log_message = pyqtSignal(str)
    status_message = pyqtSignal(str)
    finished = pyqtSignal()
    total_progress = pyqtSignal(int)
    tags_output = pyqtSignal(str)
    original_transcript_output = pyqtSignal(str)
    content_ideas_output = pyqtSignal(str)
    timestamped_summaries_output = pyqtSignal(str)
    blog_draft_output = pyqtSignal(str)
    coupang_blog_output = pyqtSignal(str)
    platform_content_output = pyqtSignal(str)
    # 숏츠 제작 관련 시그널들 추가
    shorts_script_output = pyqtSignal(str)
    shorts_hook_output = pyqtSignal(str)
    shorts_hashtags_output = pyqtSignal(str)
    shorts_timeline_output = pyqtSignal(str)
    shorts_ab_test_output = pyqtSignal(str)

class TikTokGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("틱톡 영상 다운로더 & 대본 생성기")
        self.setGeometry(200, 200, 1000, 850) # 창 크기 조정
        self.setStyleSheet("background-color: #f7f7fa;")
        self.init_ui()
        self.processor = None
        self.signals = WorkerSignals()
        self.signals.progress.connect(self.progress.setValue)
        self.signals.log_message.connect(self.log_output.append)
        self.signals.status_message.connect(self.set_status_message)
        self.signals.finished.connect(self.on_process_finished)
        self.signals.total_progress.connect(self.progress.setMaximum)
        self.signals.tags_output.connect(self.tags_output.setText)
        self.signals.original_transcript_output.connect(self.original_transcript_output.setText)
        self.signals.content_ideas_output.connect(self.content_ideas_output.setText)
        self.signals.timestamped_summaries_output.connect(self.timestamped_summaries_output.setText)
        self.signals.blog_draft_output.connect(self.blog_draft_output.setText)
        self.signals.coupang_blog_output.connect(self.coupang_blog_output.setText)
        self.signals.platform_content_output.connect(self.platform_content_output.setText)
        self.signals.shorts_script_output.connect(self.shorts_script_output.setText)
        self.signals.shorts_hook_output.connect(self.shorts_hook_output.setText)
        self.signals.shorts_hashtags_output.connect(self.shorts_hashtags_output.setText)
        self.signals.shorts_timeline_output.connect(self.shorts_timeline_output.setText)
        self.signals.shorts_ab_test_output.connect(self.shorts_ab_test_output.setText)
        self.current_thread = None # 현재 실행 중인 스레드 참조
        self.stop_event = threading.Event() # 중지 이벤트
        
        # UI 업데이트를 위한 타이머 추가
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.safe_update_ui)
        self.update_timer.start(100)  # 100ms마다 UI 업데이트

    def init_ui(self):
        font_label = QFont("Arial", 11)
        font_input = QFont("Arial", 10)
        font_btn = QFont("Arial", 11, QFont.Bold)

        self.tabs = QTabWidget() # 탭 위젯 생성
        self.tabs.setFont(font_label)
        self.tabs.setStyleSheet("QTabBar::tab { background: #e0e0e0; padding: 10px; border-top-left-radius: 5px; border-top-right-radius: 5px; } QTabBar::tab:selected { background: #4f8cff; color: white; } QTabWidget::pane { border: 1px solid #ccc; background: white; }")

        # 첫 번째 탭 (다운로드 및 분석) 내용 구성
        download_analysis_widget = QWidget()
        download_analysis_layout = QVBoxLayout()
        
        # URL 입력란
        self.url_label = QLabel("영상 또는 계정 URL:")
        self.url_label.setFont(font_label)
        self.url_label.setStyleSheet("color: #333;")
        self.url_input = QLineEdit()
        self.url_input.setFont(font_input)
        self.url_input.setStyleSheet("color: #333;")
        self.url_input.setPlaceholderText("틱톡/유튜브 영상 또는 틱톡 계정 URL을 입력하세요 (예: @homestory.official)")

        # 채널 필터링 옵션 섹션 추가
        self.filter_label = QLabel("채널 필터링 옵션 (채널 URL 입력 시 사용):")
        self.filter_label.setFont(font_label)
        self.filter_label.setStyleSheet("color: #333; font-weight: bold; margin-top: 10px;")
        
        # 필터링 옵션들을 담을 프레임
        filter_frame = QWidget()
        filter_layout = QHBoxLayout()
        filter_frame.setLayout(filter_layout)
        
        # 최소 조회수 입력
        self.min_views_label = QLabel("최소 조회수:")
        self.min_views_label.setFont(font_label)
        self.min_views_label.setStyleSheet("color: #333;")
        self.min_views_input = QLineEdit()
        self.min_views_input.setFont(font_input)
        self.min_views_input.setStyleSheet("color: #333;")
        self.min_views_input.setPlaceholderText("예: 10000")
        self.min_views_input.setFixedWidth(120)
        
        # 동영상 유형 선택
        self.video_type_label = QLabel("동영상 유형:")
        self.video_type_label.setFont(font_label)
        self.video_type_label.setStyleSheet("color: #333;")
        self.video_type_combo = QComboBox()
        self.video_type_combo.setFont(font_input)
        self.video_type_combo.setStyleSheet("color: #333;")
        self.video_type_combo.addItems(["전체", "숏폼", "롱폼"])
        self.video_type_combo.setFixedWidth(100)
        
        # 키워드 입력
        self.keywords_label = QLabel("키워드 (쉼표로 구분):")
        self.keywords_label.setFont(font_label)
        self.keywords_label.setStyleSheet("color: #333;")
        self.keywords_input = QLineEdit()
        self.keywords_input.setFont(font_input)
        self.keywords_input.setStyleSheet("color: #333;")
        self.keywords_input.setPlaceholderText("예: 리뷰, 추천, 비교")
        self.keywords_input.setFixedWidth(200)
        
        # 필터링 옵션들을 레이아웃에 추가
        filter_layout.addWidget(self.min_views_label)
        filter_layout.addWidget(self.min_views_input)
        filter_layout.addSpacing(20)
        filter_layout.addWidget(self.video_type_label)
        filter_layout.addWidget(self.video_type_combo)
        filter_layout.addSpacing(20)
        filter_layout.addWidget(self.keywords_label)
        filter_layout.addWidget(self.keywords_input)
        filter_layout.addStretch()

        # Google API Key 입력란 (새로 추가)
        self.google_api_key_label = QLabel("Google API Key (필수):")
        self.google_api_key_label.setFont(font_label)
        self.google_api_key_label.setStyleSheet("color: #333;")
        self.google_api_key_input = QLineEdit()
        self.google_api_key_input.setFont(font_input)
        self.google_api_key_input.setStyleSheet("color: #333;")
        self.google_api_key_input.setPlaceholderText("Google Gemini API Key를 입력하세요 (예: AIza...) ")
        self.google_api_key_input.setEchoMode(QLineEdit.PasswordEchoOnEdit) # 입력 시 '*'로 표시

        # 쿠팡 파트너스 상품 URL 입력란 (새로 추가)
        self.coupang_url_label = QLabel("쿠팡 파트너스 상품 URL (선택 사항):")
        self.coupang_url_label.setFont(font_label)
        self.coupang_url_label.setStyleSheet("color: #333;")
        self.coupang_url_input = QLineEdit()
        self.coupang_url_input.setFont(font_input)
        self.coupang_url_input.setStyleSheet("color: #333;")
        self.coupang_url_input.setPlaceholderText("선택 사항: 쿠팡 파트너스 상품 URL을 입력하시면 블로그 초안에 포함됩니다.")

        # 이미지 URL 입력란 (새로 추가)
        self.image_url_label = QLabel("상품 이미지 URL (선택 사항, 수동 입력):")
        self.image_url_label.setFont(font_label)
        self.image_url_label.setStyleSheet("color: #333;")
        self.image_url_input = QLineEdit()
        self.image_url_input.setFont(font_input)
        self.image_url_input.setStyleSheet("color: #333;")
        self.image_url_input.setPlaceholderText("선택 사항: 직접 이미지 URL을 입력하시면 블로그 초안에 삽입됩니다.")

        self.product_description_label = QLabel("상품 설명 (선택 사항, 자세할수록 좋습니다):")
        self.product_description_label.setFont(font_label)
        self.product_description_label.setStyleSheet("color: #333;")
        self.product_description_input = QTextEdit()
        self.product_description_input.setFont(font_input)
        self.product_description_input.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 6px; padding: 5px; color: #333;")
        self.product_description_input.setPlaceholderText("선택 사항: 제품의 특징, 장점, 대상 고객, 왜 이 제품이 좋은지 등 자세히 설명해주세요.")
        self.product_description_input.setFixedHeight(80) # 높이 조정

        # 버튼 레이아웃
        button_layout = QHBoxLayout()

        self.process_btn = QPushButton("URL 다운로드 및 대본 생성")
        self.process_btn.setFont(font_btn)
        self.process_btn.setStyleSheet("background-color: #4f8cff; color: white; padding: 10px; border-radius: 8px;")
        self.process_btn.clicked.connect(self.start_processing)
        button_layout.addWidget(self.process_btn)

        self.stop_btn = QPushButton("중지") # 중지 버튼 추가
        self.stop_btn.setFont(font_btn)
        self.stop_btn.setStyleSheet("background-color: #e74c3c; color: white; padding: 10px; border-radius: 8px;")
        self.stop_btn.clicked.connect(self.stop_processing)
        self.stop_btn.setEnabled(False) # 처음에는 비활성화
        button_layout.addWidget(self.stop_btn)

        self.open_folder_btn = QPushButton("다운로드 폴더 열기") # 폴더 열기 버튼 추가
        self.open_folder_btn.setFont(font_btn)
        self.open_folder_btn.setStyleSheet("background-color: #3498db; color: white; padding: 10px; border-radius: 8px;")
        self.open_folder_btn.clicked.connect(self.open_download_folder)
        button_layout.addWidget(self.open_folder_btn)

        self.local_transcribe_btn = QPushButton("로컬 영상 대본 생성") # 로컬 영상 대본 생성 버튼 추가
        self.local_transcribe_btn.setFont(font_btn)
        self.local_transcribe_btn.setStyleSheet("background-color: #28a745; color: white; padding: 10px; border-radius: 8px;")
        self.local_transcribe_btn.clicked.connect(self.start_local_video_transcription)
        button_layout.addWidget(self.local_transcribe_btn)

        self.load_previous_btn = QPushButton("이전 분석 결과 불러오기") # 이전 분석 결과 불러오기 버튼 추가
        self.load_previous_btn.setFont(font_btn)
        self.load_previous_btn.setStyleSheet("background-color: #6a0dad; color: white; padding: 10px; border-radius: 8px;")
        self.load_previous_btn.clicked.connect(self.load_previous_analyses)
        button_layout.addWidget(self.load_previous_btn)

        # 채널 필터링 단독 실행 버튼 추가
        self.channel_filter_btn = QPushButton("채널 필터링만 실행")
        self.channel_filter_btn.setFont(font_btn)
        self.channel_filter_btn.setStyleSheet("background-color: #17a2b8; color: white; padding: 10px; border-radius: 8px;")
        self.channel_filter_btn.clicked.connect(self.start_channel_filtering_only)
        button_layout.addWidget(self.channel_filter_btn)

        self.generate_blog_draft_btn = QPushButton("블로그 초안 생성") # 기존 블로그 초안 생성 버튼 (영상 대본 기반)
        self.generate_blog_draft_btn.setFont(font_btn)
        self.generate_blog_draft_btn.setStyleSheet("background-color: #ff8c00; color: white; padding: 10px; border-radius: 8px;")
        self.generate_blog_draft_btn.clicked.connect(self.generate_blog_draft_action) # 새 함수 연결
        self.generate_blog_draft_btn.setEnabled(False) # 처음에는 비활성화
        button_layout.addWidget(self.generate_blog_draft_btn) # 버튼 레이아웃에 추가

        # 새로운 쿠팡 블로그 초안 생성 버튼 추가
        self.generate_coupang_blog_btn = QPushButton("쿠팡 블로그 초안 생성")
        self.generate_coupang_blog_btn.setFont(font_btn)
        self.generate_coupang_blog_btn.setStyleSheet("background-color: #f0ad4e; color: white; padding: 10px; border-radius: 8px;")
        self.generate_coupang_blog_btn.clicked.connect(self.generate_coupang_blog_action) # 새 함수 연결
        self.generate_coupang_blog_btn.setEnabled(False) # 처음에는 비활성화
        button_layout.addWidget(self.generate_coupang_blog_btn)

        # 분석 결과 내보내기 버튼
        self.export_results_btn = QPushButton("분석 결과 내보내기")
        self.export_results_btn.setFont(font_btn)
        self.export_results_btn.setStyleSheet("background-color: #5cb85c; color: white; padding: 10px; border-radius: 8px;")
        self.export_results_btn.clicked.connect(self.export_all_results_action) # 새 함수 연결
        self.export_results_btn.setEnabled(False) # 처음에는 비활성화
        button_layout.addWidget(self.export_results_btn)

        # 진행률
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setStyleSheet("QProgressBar {border: 1px solid #bbb; border-radius: 6px; text-align: center;} QProgressBar::chunk {background-color: #4f8cff;}")

        # 상태 메시지 (진행률 바 아래)
        self.status_label = QLabel("준비 완료")
        self.status_label.setFont(QFont("Arial", 10))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #555;")

        # 로그 출력
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Arial", 10))
        self.log_output.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 6px; padding: 5px; color: #333;")
        
        # 태그 추출 섹션
        self.tags_label = QLabel("태그 추출:")
        self.tags_label.setFont(font_label)
        self.tags_label.setStyleSheet("color: #333;")
        self.tags_output = QTextEdit() # 태그용 QTextEdit
        self.tags_output.setReadOnly(True)
        self.tags_output.setFont(QFont("Arial", 10))
        self.tags_output.setStyleSheet("background-color: #e0f7e7; border: 1px solid #a7edd1; border-radius: 6px; padding: 5px; color: #333;")
        self.tags_output.setFixedHeight(60) # 높이 제한

        # 콘텐츠 아이디어 섹션
        self.content_ideas_label = QLabel("콘텐츠 아이디어:")
        self.content_ideas_label.setFont(font_label)
        self.content_ideas_label.setStyleSheet("color: #333;")
        self.content_ideas_output = QTextEdit()
        self.content_ideas_output.setReadOnly(True)
        self.content_ideas_output.setFont(QFont("Arial", 10))
        self.content_ideas_output.setStyleSheet("background-color: #fcefe0; border: 1px solid #edc4a7; border-radius: 6px; padding: 5px; color: #333;")
        self.content_ideas_output.setFixedHeight(120)

        # 원본 대본 내용 섹션
        self.original_transcript_label = QLabel("원본 대본 내용 (부분):")
        self.original_transcript_label.setFont(font_label)
        self.original_transcript_label.setStyleSheet("color: #333;")
        self.original_transcript_output = QTextEdit()
        self.original_transcript_output.setReadOnly(True)
        self.original_transcript_output.setFont(QFont("Arial", 10))
        self.original_transcript_output.setStyleSheet("background-color: #f2f7e0; border: 1px solid #d9eda7; border-radius: 6px; padding: 5px; color: #333;")
        self.original_transcript_output.setFixedHeight(150)

        # 영상 핵심 요약 & 타임스탬프 섹션
        self.timestamped_summaries_label = QLabel("영상 핵심 요약 & 타임스탬프:")
        self.timestamped_summaries_label.setFont(font_label)
        self.timestamped_summaries_label.setStyleSheet("color: #333;")
        self.timestamped_summaries_output = QTextEdit()
        self.timestamped_summaries_output.setReadOnly(True)
        self.timestamped_summaries_output.setFont(QFont("Arial", 10))
        self.timestamped_summaries_output.setStyleSheet("background-color: #e0f0fc; border: 1px solid #a7d9ed; border-radius: 6px; padding: 5px; color: #333;")
        self.timestamped_summaries_output.setFixedHeight(150)

        # 블로그 초안 섹션 (기존 영상 대본 기반)
        self.blog_draft_label = QLabel("블로그 초안 (영상 대본 기반):")
        self.blog_draft_label.setFont(font_label)
        self.blog_draft_label.setStyleSheet("color: #333;")
        self.blog_draft_output = QTextEdit()
        self.blog_draft_output.setReadOnly(True)
        self.blog_draft_output.setFont(QFont("Arial", 10))
        self.blog_draft_output.setStyleSheet("background-color: #fffacd; border: 1px solid #daac00; border-radius: 6px; padding: 5px; color: #333;")
        self.blog_draft_output.setFixedHeight(200) # 높이 제한

        # 생성된 쿠팡 블로그 초안 섹션 (이동됨)
        self.coupang_blog_output_label = QLabel("생성된 쿠팡 블로그 초안:")
        self.coupang_blog_output_label.setFont(font_label)
        self.coupang_blog_output_label.setStyleSheet("color: #333;")
        self.coupang_blog_output = QTextEdit()
        self.coupang_blog_output.setReadOnly(True)
        self.coupang_blog_output.setFont(QFont("Arial", 10))
        self.coupang_blog_output.setStyleSheet("background-color: #fff8e1; border: 1px solid #ffe0b2; border-radius: 6px; padding: 5px; color: #333;")
        self.coupang_blog_output.setFixedHeight(300)

        download_analysis_layout.addWidget(self.url_label)
        download_analysis_layout.addWidget(self.url_input)
        download_analysis_layout.addWidget(self.filter_label)  # 필터링 옵션 라벨 추가
        download_analysis_layout.addWidget(filter_frame)  # 필터링 옵션 프레임 추가
        download_analysis_layout.addWidget(self.google_api_key_label) # API Key 입력란 추가
        download_analysis_layout.addWidget(self.google_api_key_input) # API Key 입력란 추가
        download_analysis_layout.addWidget(self.coupang_url_label)
        download_analysis_layout.addWidget(self.coupang_url_input)
        download_analysis_layout.addWidget(self.image_url_label) # 이미지 URL 입력란 추가
        download_analysis_layout.addWidget(self.image_url_input) # 이미지 URL 입력란 추가
        download_analysis_layout.addWidget(self.product_description_label)
        download_analysis_layout.addWidget(self.product_description_input)
        download_analysis_layout.addLayout(button_layout)
        download_analysis_layout.addWidget(self.progress)
        download_analysis_layout.addWidget(self.status_label)
        download_analysis_layout.addWidget(self.log_output)
        download_analysis_layout.addWidget(self.tags_label)
        download_analysis_layout.addWidget(self.tags_output)
        download_analysis_layout.addWidget(self.content_ideas_label)
        download_analysis_layout.addWidget(self.content_ideas_output)
        download_analysis_layout.addWidget(self.original_transcript_label)
        download_analysis_layout.addWidget(self.original_transcript_output)
        download_analysis_layout.addWidget(self.timestamped_summaries_label)
        download_analysis_layout.addWidget(self.timestamped_summaries_output)
        download_analysis_layout.addWidget(self.blog_draft_label)
        download_analysis_layout.addWidget(self.blog_draft_output)
        download_analysis_layout.addWidget(self.coupang_blog_output_label)
        download_analysis_layout.addWidget(self.coupang_blog_output)


        download_analysis_scroll_widget = QWidget()
        download_analysis_scroll_widget.setLayout(download_analysis_layout)

        self.tabs.addTab(download_analysis_scroll_widget, "다운로드 및 분석")

        # 두 번째 탭 (콘텐츠 최적화) 내용 구성
        content_optimization_widget = QWidget()
        content_optimization_layout = QVBoxLayout()

        self.platform_selection_label = QLabel("콘텐츠를 생성할 플랫폼을 선택하세요:")
        self.platform_selection_label.setFont(font_label)
        self.platform_selection_label.setStyleSheet("color: #333;")
        self.platform_combobox = QComboBox()
        self.platform_combobox.setFont(font_input)
        self.platform_combobox.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 6px; padding: 5px; color: #333;")
        self.platform_combobox.addItems(["instagram", "youtube_description", "threads", "twitter"])

        self.generate_platform_content_btn = QPushButton("플랫폼 최적화 콘텐츠 생성")
        self.generate_platform_content_btn.setFont(font_btn)
        self.generate_platform_content_btn.setStyleSheet("background-color: #007bff; color: white; padding: 10px; border-radius: 8px;")
        self.generate_platform_content_btn.clicked.connect(self.generate_platform_optimized_content_action)
        self.generate_platform_content_btn.setEnabled(False) # 분석 결과 로드 후 활성화

        self.platform_content_output_label = QLabel("생성된 플랫폼 최적화 콘텐츠:")
        self.platform_content_output_label.setFont(font_label)
        self.platform_content_output_label.setStyleSheet("color: #333;")
        self.platform_content_output = QTextEdit()
        self.platform_content_output.setReadOnly(True)
        self.platform_content_output.setFont(QFont("Arial", 10))
        self.platform_content_output.setStyleSheet("background-color: #e0f9fd; border: 1px solid #b2ebf2; border-radius: 6px; padding: 5px; color: #333;")
        # self.platform_content_output.setFixedHeight(400) # 높이 조정 (고정 높이 제거)

        content_optimization_layout.addWidget(self.platform_selection_label)
        content_optimization_layout.addWidget(self.platform_combobox)
        content_optimization_layout.addWidget(self.generate_platform_content_btn)
        content_optimization_layout.addWidget(self.platform_content_output_label)
        content_optimization_layout.addWidget(self.platform_content_output)

        content_optimization_layout.setContentsMargins(15, 15, 15, 15) # 여백 추가
        content_optimization_layout.setSpacing(10) # 위젯 간 간격 추가

        content_optimization_widget.setLayout(content_optimization_layout)

        self.tabs.addTab(content_optimization_widget, "콘텐츠 최적화") # 새 탭 추가

        # 세 번째 탭 (숏츠 제작 지원) 내용 구성
        shorts_creation_widget = QWidget()
        shorts_creation_layout = QVBoxLayout()

        # 숏츠 제작 설정 섹션
        shorts_settings_label = QLabel("숏츠 제작 설정:")
        shorts_settings_label.setFont(font_label)
        shorts_settings_label.setStyleSheet("color: #333; font-weight: bold; margin-top: 10px;")
        
        # 숏츠 길이 선택
        shorts_length_label = QLabel("숏츠 길이:")
        shorts_length_label.setFont(font_label)
        shorts_length_label.setStyleSheet("color: #333;")
        self.shorts_length_combo = QComboBox()
        self.shorts_length_combo.setFont(font_input)
        self.shorts_length_combo.setStyleSheet("color: #333;")
        self.shorts_length_combo.addItems(["15초", "30초", "60초"])
        self.shorts_length_combo.setFixedWidth(100)
        
        # 플랫폼 선택
        shorts_platform_label = QLabel("타겟 플랫폼:")
        shorts_platform_label.setFont(font_label)
        shorts_platform_label.setStyleSheet("color: #333;")
        self.shorts_platform_combo = QComboBox()
        self.shorts_platform_combo.setFont(font_input)
        self.shorts_platform_combo.setStyleSheet("color: #333;")
        self.shorts_platform_combo.addItems(["TikTok", "YouTube Shorts", "Instagram Reels", "전체"])
        self.shorts_platform_combo.setFixedWidth(150)
        
        # 콘텐츠 유형 선택
        shorts_type_label = QLabel("콘텐츠 유형:")
        shorts_type_label.setFont(font_label)
        shorts_type_label.setStyleSheet("color: #333;")
        self.shorts_type_combo = QComboBox()
        self.shorts_type_combo.setFont(font_input)
        self.shorts_type_combo.setStyleSheet("color: #333;")
        self.shorts_type_combo.addItems(["교육/정보", "엔터테인먼트", "제품 리뷰", "라이프스타일", "요리/음식", "기타"])
        self.shorts_type_combo.setFixedWidth(150)
        
        # 설정 옵션들을 담을 프레임
        shorts_settings_frame = QWidget()
        shorts_settings_layout = QHBoxLayout()
        shorts_settings_frame.setLayout(shorts_settings_layout)
        
        shorts_settings_layout.addWidget(shorts_length_label)
        shorts_settings_layout.addWidget(self.shorts_length_combo)
        shorts_settings_layout.addSpacing(20)
        shorts_settings_layout.addWidget(shorts_platform_label)
        shorts_settings_layout.addWidget(self.shorts_platform_combo)
        shorts_settings_layout.addSpacing(20)
        shorts_settings_layout.addWidget(shorts_type_label)
        shorts_settings_layout.addWidget(self.shorts_type_combo)
        shorts_settings_layout.addStretch()

        # 숏츠 제작 버튼들
        shorts_buttons_layout = QHBoxLayout()
        
        self.generate_shorts_script_btn = QPushButton("숏츠 스크립트 생성")
        self.generate_shorts_script_btn.setFont(font_btn)
        self.generate_shorts_script_btn.setStyleSheet("background-color: #ff6b6b; color: white; padding: 10px; border-radius: 8px;")
        self.generate_shorts_script_btn.clicked.connect(self.generate_shorts_script_action)
        self.generate_shorts_script_btn.setEnabled(False)
        shorts_buttons_layout.addWidget(self.generate_shorts_script_btn)
        
        self.generate_shorts_hook_btn = QPushButton("후크(Hook) 생성")
        self.generate_shorts_hook_btn.setFont(font_btn)
        self.generate_shorts_hook_btn.setStyleSheet("background-color: #4ecdc4; color: white; padding: 10px; border-radius: 8px;")
        self.generate_shorts_hook_btn.clicked.connect(self.generate_shorts_hook_action)
        self.generate_shorts_hook_btn.setEnabled(False)
        shorts_buttons_layout.addWidget(self.generate_shorts_hook_btn)
        
        self.generate_shorts_hashtags_btn = QPushButton("해시태그 최적화")
        self.generate_shorts_hashtags_btn.setFont(font_btn)
        self.generate_shorts_hashtags_btn.setStyleSheet("background-color: #45b7d1; color: white; padding: 10px; border-radius: 8px;")
        self.generate_shorts_hashtags_btn.clicked.connect(self.generate_shorts_hashtags_action)
        self.generate_shorts_hashtags_btn.setEnabled(False)
        shorts_buttons_layout.addWidget(self.generate_shorts_hashtags_btn)
        
        self.generate_shorts_timeline_btn = QPushButton("편집 타임라인 생성")
        self.generate_shorts_timeline_btn.setFont(font_btn)
        self.generate_shorts_timeline_btn.setStyleSheet("background-color: #96ceb4; color: white; padding: 10px; border-radius: 8px;")
        self.generate_shorts_timeline_btn.clicked.connect(self.generate_shorts_timeline_action)
        self.generate_shorts_timeline_btn.setEnabled(False)
        shorts_buttons_layout.addWidget(self.generate_shorts_timeline_btn)
        
        self.generate_shorts_ab_test_btn = QPushButton("A/B 테스트 시나리오")
        self.generate_shorts_ab_test_btn.setFont(font_btn)
        self.generate_shorts_ab_test_btn.setStyleSheet("background-color: #feca57; color: white; padding: 10px; border-radius: 8px;")
        self.generate_shorts_ab_test_btn.clicked.connect(self.generate_shorts_ab_test_action)
        self.generate_shorts_ab_test_btn.setEnabled(False)
        shorts_buttons_layout.addWidget(self.generate_shorts_ab_test_btn)

        # 숏츠 제작 결과 내보내기 버튼 추가
        self.export_shorts_results_btn = QPushButton("숏츠 제작 결과 내보내기")
        self.export_shorts_results_btn.setFont(font_btn)
        self.export_shorts_results_btn.setStyleSheet("background-color: #6c5ce7; color: white; padding: 10px; border-radius: 8px;")
        self.export_shorts_results_btn.clicked.connect(self.export_shorts_results_action)
        self.export_shorts_results_btn.setEnabled(False)
        shorts_buttons_layout.addWidget(self.export_shorts_results_btn)

        # 숏츠 제작 결과 출력 섹션들
        # 숏츠 스크립트 출력
        self.shorts_script_label = QLabel("숏츠 스크립트:")
        self.shorts_script_label.setFont(font_label)
        self.shorts_script_label.setStyleSheet("color: #333;")
        self.shorts_script_output = QTextEdit()
        self.shorts_script_output.setReadOnly(True)
        self.shorts_script_output.setFont(QFont("Arial", 10))
        self.shorts_script_output.setStyleSheet("background-color: #ffe6e6; border: 1px solid #ffb3b3; border-radius: 6px; padding: 5px; color: #333;")
        self.shorts_script_output.setFixedHeight(150)
        
        # 후크 출력
        self.shorts_hook_label = QLabel("후크(Hook) 제안:")
        self.shorts_hook_label.setFont(font_label)
        self.shorts_hook_label.setStyleSheet("color: #333;")
        self.shorts_hook_output = QTextEdit()
        self.shorts_hook_output.setReadOnly(True)
        self.shorts_hook_output.setFont(QFont("Arial", 10))
        self.shorts_hook_output.setStyleSheet("background-color: #e6f7f7; border: 1px solid #b3e6e6; border-radius: 6px; padding: 5px; color: #333;")
        self.shorts_hook_output.setFixedHeight(120)
        
        # 해시태그 출력
        self.shorts_hashtags_label = QLabel("최적화된 해시태그:")
        self.shorts_hashtags_label.setFont(font_label)
        self.shorts_hashtags_label.setStyleSheet("color: #333;")
        self.shorts_hashtags_output = QTextEdit()
        self.shorts_hashtags_output.setReadOnly(True)
        self.shorts_hashtags_output.setFont(QFont("Arial", 10))
        self.shorts_hashtags_output.setStyleSheet("background-color: #e6f0f7; border: 1px solid #b3d9e6; border-radius: 6px; padding: 5px; color: #333;")
        self.shorts_hashtags_output.setFixedHeight(100)
        
        # 편집 타임라인 출력
        self.shorts_timeline_label = QLabel("편집 타임라인:")
        self.shorts_timeline_label.setFont(font_label)
        self.shorts_timeline_label.setStyleSheet("color: #333;")
        self.shorts_timeline_output = QTextEdit()
        self.shorts_timeline_output.setReadOnly(True)
        self.shorts_timeline_output.setFont(QFont("Arial", 10))
        self.shorts_timeline_output.setStyleSheet("background-color: #e6f7e6; border: 1px solid #b3e6b3; border-radius: 6px; padding: 5px; color: #333;")
        self.shorts_timeline_output.setFixedHeight(150)
        
        # A/B 테스트 시나리오 출력
        self.shorts_ab_test_label = QLabel("A/B 테스트 시나리오:")
        self.shorts_ab_test_label.setFont(font_label)
        self.shorts_ab_test_label.setStyleSheet("color: #333;")
        self.shorts_ab_test_output = QTextEdit()
        self.shorts_ab_test_output.setReadOnly(True)
        self.shorts_ab_test_output.setFont(QFont("Arial", 10))
        self.shorts_ab_test_output.setStyleSheet("background-color: #fff7e6; border: 1px solid #ffe6b3; border-radius: 6px; padding: 5px; color: #333;")
        self.shorts_ab_test_output.setFixedHeight(200)

        # 레이아웃에 위젯들 추가
        shorts_creation_layout.addWidget(shorts_settings_label)
        shorts_creation_layout.addWidget(shorts_settings_frame)
        shorts_creation_layout.addLayout(shorts_buttons_layout)
        shorts_creation_layout.addWidget(self.shorts_script_label)
        shorts_creation_layout.addWidget(self.shorts_script_output)
        shorts_creation_layout.addWidget(self.shorts_hook_label)
        shorts_creation_layout.addWidget(self.shorts_hook_output)
        shorts_creation_layout.addWidget(self.shorts_hashtags_label)
        shorts_creation_layout.addWidget(self.shorts_hashtags_output)
        shorts_creation_layout.addWidget(self.shorts_timeline_label)
        shorts_creation_layout.addWidget(self.shorts_timeline_output)
        shorts_creation_layout.addWidget(self.shorts_ab_test_label)
        shorts_creation_layout.addWidget(self.shorts_ab_test_output)

        shorts_creation_layout.setContentsMargins(15, 15, 15, 15)
        shorts_creation_layout.setSpacing(10)

        shorts_creation_widget.setLayout(shorts_creation_layout)

        self.tabs.addTab(shorts_creation_widget, "숏츠 제작 지원") # 새 탭 추가

        main_layout = QVBoxLayout()
        full_app_scroll_area = QScrollArea() # 전체 앱을 위한 스크롤 영역 추가
        full_app_scroll_area.setWidgetResizable(True)
        full_app_scroll_area.setWidget(self.tabs)
        main_layout.addWidget(full_app_scroll_area)
        self.setLayout(main_layout)

    def set_status_message(self, message):
        self.status_label.setText(message)

    def start_processing(self):
        url = self.url_input.text().strip()
        coupang_url = self.coupang_url_input.text().strip() # 쿠팡 URL 가져오기
        product_description = self.product_description_input.toPlainText().strip() # 상품 설명 가져오기
        google_api_key = self.google_api_key_input.text().strip() # Google API Key 가져오기
        
        # 필터링 옵션 가져오기
        min_views_text = self.min_views_input.text().strip()
        min_views = int(min_views_text) if min_views_text.isdigit() else None
        video_type = self.video_type_combo.currentText()
        if video_type == "전체":
            video_type = None
        keywords = self.keywords_input.text().strip() if self.keywords_input.text().strip() else None

        if not url:
            QMessageBox.warning(self, "입력 오류", "영상 URL을 입력해주세요.")
            return
        
        if not google_api_key:
            QMessageBox.warning(self, "입력 오류", "Google API Key를 입력해주세요.")
            return
        
        self.signals.log_message.emit(f"<b>\nURL 처리 시작: {url}</b>")
        if min_views or video_type or keywords:
            self.signals.log_message.emit(f"<b>필터 조건: 최소 조회수={min_views}, 유형={video_type}, 키워드={keywords}</b>")
        
        self.progress.setValue(0)
        self.status_label.setText("처리 중...")
        self.tags_output.clear()
        self.content_ideas_output.clear()
        self.original_transcript_output.clear()
        self.timestamped_summaries_output.clear()
        self.blog_draft_output.clear()
        self.coupang_blog_output.clear() # 쿠팡 블로그 출력 초기화

        self.process_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(False)
        self.local_transcribe_btn.setEnabled(False)
        self.generate_blog_draft_btn.setEnabled(False)
        self.export_results_btn.setEnabled(False)

        self.stop_event.clear()

        self.processor = VideoProcessor(stop_event=self.stop_event, api_key=google_api_key) # API Key 전달

        # 채널 URL인지 확인하고 필터링 옵션이 있는지 확인
        is_channel_url = re.match(r'^https?://(www\.)?tiktok\.com/@[\w.]+/?(?:\?.*)?$', url) or \
                        re.match(r'^https?://(www\.)?douyin\.com/@[\w.]+/?(?:\\?.*)?$', url) or \
                        re.match(r'^https?://(www\.)?youtube\.com/(channel|user|c)/[\w.-]+/?', url) or \
                        re.match(r'^https?://(www\.)?youtube\.com/@[\w.-]+/?', url)
        
        has_filters = min_views is not None or video_type is not None or keywords is not None
        
        if is_channel_url and has_filters:
            # 채널 URL이고 필터링 옵션이 있는 경우
            self.signals.log_message.emit(f"<b>채널 URL + 필터링 감지: {url}</b>")
            self.current_thread = threading.Thread(
                target=self._process_channel_with_filters_thread, 
                args=(url, min_views, video_type, keywords, coupang_url, product_description,), 
                daemon=True
            )
        elif re.match(r'^https?://(www\.)?tiktok\.com/@[\w.]+/?(?:\?.*)?$', url) or \
             re.match(r'^https?://(www\.)?douyin\.com/@[\w.]+/?(?:\\?.*)?$', url): # Douyin 계정 URL 포함
            # 기존 계정 처리 (필터링 없음)
            self.signals.log_message.emit(f"<b>계정 URL 감지: {url}</b>")
            self.current_thread = threading.Thread(target=self._process_profile_videos_thread, args=(url, coupang_url, product_description,), daemon=True)
        else:
            # 단일 영상 URL
            self.signals.log_message.emit(f"<b>단일 영상 URL 감지: {url}</b>")
            self.current_thread = threading.Thread(target=self._process_single_video_thread, args=(url, coupang_url, product_description,), daemon=True)

        self.current_thread.start()

    def start_local_video_transcription(self):
        file_dialog = QFileDialog()
        file_dialog.setNameFilter("Videos (*.mp4 *.mov *.avi *.mkv)")
        file_dialog.setWindowTitle("로컬 영상 파일 선택")
        if file_dialog.exec_():
            video_path = file_dialog.selectedFiles()[0]
            google_api_key = self.google_api_key_input.text().strip() # Google API Key 가져오기

            if not google_api_key:
                QMessageBox.warning(self, "입력 오류", "Google API Key를 입력해주세요.")
                self.signals.log_message.emit("<span style='color:red;'>로컬 영상 대본 생성 실패: Google API Key 없음.</span>")
                return

            self.signals.log_message.emit(f"<b>\n로컬 영상 대본 생성 시작: {video_path}</b>")
            self.progress.setValue(0)
            self.status_label.setText("로컬 영상 처리 중...")
            self.tags_output.clear()
            self.content_ideas_output.clear()
            self.original_transcript_output.clear()
            self.timestamped_summaries_output.clear()
            self.blog_draft_output.clear()
            self.coupang_blog_output.clear() # 쿠팡 블로그 출력 초기화
            self.process_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.open_folder_btn.setEnabled(False)
            self.local_transcribe_btn.setEnabled(False)
            self.generate_blog_draft_btn.setEnabled(False)
            self.stop_event.clear()

            self.processor = VideoProcessor(stop_event=self.stop_event, api_key=google_api_key) # API Key 전달
            # 로컬 영상 대본 생성에서는 쿠팡 URL/상품 설명 인자를 사용하지 않으므로, 기본값으로 빈 문자열 전달
            self.current_thread = threading.Thread(target=self._process_local_video_for_transcript_thread, args=(video_path,), daemon=True)
            self.current_thread.start()
        else:
            self.signals.log_message.emit("로컬 영상 선택 취소됨.")

    def stop_processing(self):
        self.signals.log_message.emit("<b>\n작업 중지 요청...</b>")
        self.stop_event.set()
        self.process_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("중지 중...")

    def open_download_folder(self):
        download_path = str(Path("downloads"))
        if not os.path.exists(download_path):
            os.makedirs(download_path)
            
        if platform.system() == "Windows":
            os.startfile(download_path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", download_path])
        else:
            try:
                subprocess.Popen(["xdg-open", download_path])
            except OSError:
                QMessageBox.warning(self, "오류", "지원되지 않는 운영체제입니다. 폴더를 수동으로 여세요.")

    def open_link(self, url):
        webbrowser.open(url.toString())

    def load_previous_analyses(self):
        self.signals.log_message.emit("<b>이전 분석 결과 불러오기 시작...</b>")
        self.progress.setValue(0)
        self.status_label.setText("이전 분석 결과 로드 중...")
        self.tags_output.clear()
        self.content_ideas_output.clear()
        self.original_transcript_output.clear()
        self.timestamped_summaries_output.clear()
        self.blog_draft_output.clear()
        self.coupang_blog_output.clear() # 쿠팡 블로그 출력 초기화

        self.process_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)
        self.local_transcribe_btn.setEnabled(False)
        self.load_previous_btn.setEnabled(False)
        self.generate_blog_draft_btn.setEnabled(False)

        try:
            google_api_key = self.google_api_key_input.text().strip() # Google API Key 가져오기

            if not google_api_key:
                QMessageBox.warning(self, "입력 오류", "Google API Key를 입력해주세요.")
                self.signals.log_message.emit("<span style='color:red;'>이전 분석 로드 실패: Google API Key 없음.</span>")
                return

            self.processor = VideoProcessor(stop_event=self.stop_event, api_key=google_api_key) # 새로운 프로세서 인스턴스 생성 (stop_event와 API Key 전달)
            previous_analyses = self.processor.get_previous_analyses()

            if not previous_analyses:
                QMessageBox.information(self, "정보", "이전에 분석된 영상이 없습니다.")
                self.signals.log_message.emit("<span style='color:orange;'>이전에 분석된 영상 없음.</span>")
                return

            items = [f"{item['video_title']} (업로더: {item['uploader']})" for item in previous_analyses]
            item_map = {items[i]: previous_analyses[i] for i in range(len(items))}

            dialog = QInputDialog(self)
            dialog.setWindowTitle("이전 분석 결과 선택")
            dialog.setLabelText("로드할 영상을 선택하세요:")
            dialog.setComboBoxItems(items)
            dialog.setOkButtonText("확인")
            dialog.setCancelButtonText("취소")
            
            dialog.setStyleSheet("""
                QInputDialog { color: black; background-color: white; }
                QLabel { color: black; }
                QLineEdit { color: black; background-color: white; }
                QComboBox {
                    color: black;
                    background-color: white;
                    selection-background-color: #a0a0a0;
                    combobox-popup: 0;
                }
                QComboBox QLineEdit { color: black; } /* 콤보박스 입력 필드 텍스트 색상 */
                QComboBox:on {
                    padding-top: 0px;
                    padding-left: 4px;
                    color: black;
                }
                QComboBox QAbstractItemView { color: black; background-color: white; selection-background-color: #a0a0a0; } /* 콤보박스 드롭다운 목록 */
                QComboBox::item { color: black; } /* 콤보박스 아이템 일반 상태 */
                QComboBox::item:selected { color: black; background-color: #a0a0a0; } /* 콤보박스 아이템 선택 상태 */
                QListView {
                    color: black;
                    background-color: white;
                    selection-background-color: #a0a0a0;
                    alternate-background-color: #f5f5f5;
                }
                QListView::item {
                    color: black;
                    selection-color: black;
                    selection-background-color: #a0a0a0;
                }
                QPushButton {
                    color: black;
                    background-color: #e0e0e0;
                    border: 1px solid #c0c0c0;
                    border-radius: 3px;
                }
                QPushButton:hover { background-color: #d0d0d0; }
            """)

            ok = dialog.exec_()
            item = dialog.textValue() if ok else ""

            if ok and item:
                selected_analysis_info = item_map[item]
                analysis_file_path = selected_analysis_info['analysis_file_path']
                video_id = selected_analysis_info['video_id']
                uploader_name = selected_analysis_info['uploader']

                self.signals.log_message.emit(f"<b>' {selected_analysis_info['video_title']} ' 분석 결과 로드 중...</b>")
                
                with open(analysis_file_path, "r", encoding="utf-8") as f:
                    analysis_data = json.load(f)

                transcript_file_path = Path(self.processor.download_dir) / uploader_name / "video_scripts" / f"{video_id}_transcript.json"
                transcript_content = ""
                if transcript_file_path.exists():
                    with open(transcript_file_path, "r", encoding="utf-8") as f:
                        transcript_data = json.load(f)
                        transcript_content = transcript_data.get('transcript_text', '')
                else:
                    self.signals.log_message.emit(f"<span style='color:orange;'>경고: 대본 파일 {transcript_file_path}을 찾을 수 없습니다.</span>")

                tags_text = ", ".join(analysis_data.get('suggested_tags', []))
                self.signals.tags_output.emit(tags_text)
                self.signals.log_message.emit(f"\n<b>[로드된 태그]</b>\n{tags_text}")

                loaded_content_ideas_list = analysis_data.get('blog_post_ideas', []) + analysis_data.get('new_video_ideas', [])
                loaded_content_ideas_text = "\n".join([f"- {idea}" for idea in loaded_content_ideas_list])
                self.signals.content_ideas_output.emit(loaded_content_ideas_text)
                self.signals.log_message.emit(f"\n<b>[로드된 콘텐츠 아이디어]</b>\n{loaded_content_ideas_text}")

                original_transcript_preview = transcript_content[:1000] + "..." if len(transcript_content) > 1000 else transcript_content if transcript_content else "대본 없음"
                print(f"[DEBUG_GUI] 원본 대본 내용 (미리보기): {original_transcript_preview[:100]}...")
                self.signals.original_transcript_output.emit(original_transcript_preview)
                self.signals.log_message.emit(f"\n<b>[로드된 원본 대본 내용 (부분)]</b>\n{original_transcript_preview}")
                
                timestamped_summaries_list = analysis_data.get('timestamped_summaries', [])
                timestamped_summaries_text = ""
                for summary in timestamped_summaries_list:
                    start_time = str(int(summary['start'] // 60)).zfill(2) + ":" + str(int(summary['start'] % 60)).zfill(2)
                    end_time = str(int(summary['end'] // 60)).zfill(2) + ":" + str(int(summary['end'] % 60)).zfill(2)
                    timestamped_summaries_text += f"[{start_time}-{end_time}] {summary['text']}\n"
                print(f"[DEBUG_GUI] 타임스탬프 요약: {timestamped_summaries_text[:100]}...")
                self.signals.timestamped_summaries_output.emit(timestamped_summaries_text)
                self.signals.log_message.emit(f"\n<b>[로드된 영상 핵심 요약 & 타임스탬프]</b>\n{timestamped_summaries_text}")

                self.signals.log_message.emit("<span style='color:green;'>분석 결과 로드 완료!</span>")
                self.signals.status_message.emit("로드 완료")
                self.progress.setValue(100)

                self.generate_blog_draft_btn.setEnabled(True)
                self.generate_coupang_blog_btn.setEnabled(True)
                self.export_results_btn.setEnabled(True)
                self.generate_platform_content_btn.setEnabled(True) # 플랫폼 최적화 버튼 활성화
                self.last_loaded_transcript_content = transcript_content
                self.last_loaded_video_title = selected_analysis_info['video_title']

                # 쿠팡 파트너스 관련 데이터 저장 (초안 생성은 버튼 클릭 시)
                self.last_coupang_url = coupang_url
                self.last_product_description = product_description
                self.last_transcript_for_coupang = transcript_content
                self.last_analysis_results_for_coupang = analysis_data # 분석 결과도 저장

                if coupang_url and not product_description:
                    self.signals.log_message.emit("<span style='color:blue;'>상품 설명이 비어있습니다. '쿠팡 블로그 초안 생성' 버튼 클릭 시, 분석된 영상 내용과 태그를 기반으로 상품 설명이 자동으로 생성됩니다.</span>")
                elif coupang_url and self.processor.gemini_model:
                    self.signals.log_message.emit("<span style='color:blue;'>쿠팡 파트너스 URL과 상품 설명이 입력되었습니다. '쿠팡 블로그 초안 생성' 버튼을 클릭하여 블로그 초안을 생성하세요.</span>")
                elif (coupang_url or product_description) and not self.processor.gemini_model:
                    self.signals.log_message.emit("<span style='color:orange;'>쿠팡 파트너스 URL 또는 상품 설명이 입력되었으나, Gemini 모델이 준비되지 않아 쿠팡 블로그 초안을 생성할 수 없습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.</span>")

            else:
                self.signals.log_message.emit("<span style='color:orange;'>영상 선택 취소됨.</span>")
                self.signals.status_message.emit("취소됨")

        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>이전 분석 로드 중 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.process_btn.setEnabled(True)
            self.open_folder_btn.setEnabled(True)
            self.local_transcribe_btn.setEnabled(True)
            self.load_previous_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def _process_single_video_thread(self, url, coupang_url, product_description):
        """단일 영상 처리 스레드"""
        audio_path = None
        try:
            self.signals.log_message.emit("영상 다운로드 중...")
            self.signals.progress.emit(10)
            
            video_info = self.processor.download_video_from_url(url)
            
            if not video_info:
                if self.stop_event.is_set():
                    self.signals.log_message.emit("<span style='color:orange;'>작업이 중지되었습니다.</span>")
                    self.signals.status_message.emit("중지됨")
                else:
                    self.signals.log_message.emit("<span style='color:red;'>영상 다운로드 실패</span>")
                    self.signals.status_message.emit("실패: 다운로드 오류")
                return
            
            downloaded_path = video_info.get('downloaded_path')
            if not downloaded_path or not os.path.exists(downloaded_path):
                self.signals.log_message.emit("<span style='color:red;'>다운로드된 영상 파일을 찾을 수 없습니다.</span>")
                self.signals.status_message.emit("실패: 파일 없음")
                return

            self.signals.log_message.emit(f"영상 다운로드 완료: {downloaded_path}")
            self.signals.progress.emit(40)

            self.signals.log_message.emit("오디오 추출 중...")
            audio_path = self.processor.extract_audio(downloaded_path)
            if not audio_path:
                if self.stop_event.is_set():
                    self.signals.log_message.emit("<span style='color:orange;'>작업이 중지되었습니다.</span>")
                    self.signals.status_message.emit("중지됨")
                else:
                    self.signals.log_message.emit("<span style='color:red;'>오디오 추출 실패</span>")
                    self.signals.status_message.emit("실패: 오디오 추출 오류")
                return
            self.signals.log_message.emit(f"오디오 추출 완료: {audio_path}")
            self.signals.progress.emit(70)

            self.signals.log_message.emit("대본 생성 중...")
            self.signals.progress.emit(70)

            transcript_text = self.processor.generate_transcript(audio_path)
            if transcript_text is None:
                raise Exception("대본 생성 실패: Whisper 모델이 텍스트를 반환하지 않았습니다.")
            print(f"[DEBUG_GUI] Whisper 대본 생성 결과: {transcript_text[:50]}...")
            whisper_result = {"text": transcript_text, "segments": []}

            self.signals.log_message.emit("대본 저장 중...")
            print("[DEBUG_GUI] save_transcript 호출 전.")
            transcript_success = self.processor.save_transcript(video_info, whisper_result)
            print(f"[DEBUG_GUI] save_transcript 호출 후. 결과: {transcript_success}")
            if not transcript_success:
                raise Exception("대본 저장 실패.")

            self.signals.log_message.emit("콘텐츠 분석 중...")
            print("[DEBUG_GUI] analyze_video_content 호출 전.")
            analysis_results = self.processor.analyze_video_content(video_info, whisper_result)
            print(f"[DEBUG_GUI] analyze_video_content 호출 후. 결과: {analysis_results is not None}")
            if analysis_results is None:
                raise Exception("콘텐츠 분석 실패.")

            analysis_success = self.processor.save_analysis_results(video_info, analysis_results)
            print(f"[DEBUG_GUI] save_analysis_results 호출 후. 결과: {analysis_success}")
            if not analysis_success:
                raise Exception("분석 결과 저장 실패.")

            # GUI에 분석 결과 표시
            tags_text = ", ".join(analysis_results.get('suggested_tags', []))
            self.signals.tags_output.emit(tags_text)
            self.signals.log_message.emit(f"\n<b>[태그 추출]</b>\n{tags_text}")

            content_ideas_list = analysis_results.get('content_ideas', [])
            content_ideas_text = "\n".join([f"- {idea}" for idea in content_ideas_list])
            self.signals.content_ideas_output.emit(content_ideas_text)
            self.signals.log_message.emit(f"\n<b>[콘텐츠 아이디어]</b>\n{content_ideas_text}")

            original_transcript_preview = transcript_text[:1000] + "..." if len(transcript_text) > 1000 else transcript_text
            self.signals.original_transcript_output.emit(original_transcript_preview)
            self.signals.log_message.emit(f"\n<b>[원본 대본 내용 (부분)]</b>\n{original_transcript_preview}")

            timestamped_summaries_list = analysis_results.get('timestamped_summaries', [])
            timestamped_summaries_text = ""
            for summary in timestamped_summaries_list:
                start_time = str(int(summary['start'] // 60)).zfill(2) + ":" + str(int(summary['start'] % 60)).zfill(2)
                end_time = str(int(summary['end'] // 60)).zfill(2) + ":" + str(int(summary['end'] % 60)).zfill(2)
                timestamped_summaries_text += f"[{start_time}-{end_time}] {summary['text']}\n"
            self.signals.timestamped_summaries_output.emit(timestamped_summaries_text)
            self.signals.log_message.emit(f"\n<b>[영상 핵심 요약 & 타임스탬프]</b>\n{timestamped_summaries_text}")

            self.signals.log_message.emit("모든 작업 완료.")
            self.signals.status_message.emit("성공")
            self.progress.setValue(100)

            self.generate_blog_draft_btn.setEnabled(True)
            self.generate_coupang_blog_btn.setEnabled(True)
            self.export_results_btn.setEnabled(True)
            self.generate_platform_content_btn.setEnabled(True) # 플랫폼 최적화 버튼 활성화
            self.last_loaded_transcript_content = transcript_text
            self.last_loaded_video_title = video_info.get('video_title', '제목 없음')

            # 쿠팡 파트너스 관련 데이터 저장 (초안 생성은 버튼 클릭 시)
            self.last_coupang_url = coupang_url
            self.last_product_description = product_description
            self.last_transcript_for_coupang = transcript_text
            self.last_analysis_results_for_coupang = analysis_results # 분석 결과도 저장

            if coupang_url and not product_description:
                self.signals.log_message.emit("<span style='color:blue;'>상품 설명이 비어있습니다. '쿠팡 블로그 초안 생성' 버튼 클릭 시, 분석된 영상 내용과 태그를 기반으로 상품 설명이 자동으로 생성됩니다.</span>")
            elif coupang_url and self.processor.gemini_model:
                self.signals.log_message.emit("<span style='color:blue;'>쿠팡 파트너스 URL과 상품 설명이 입력되었습니다. '쿠팡 블로그 초안 생성' 버튼을 클릭하여 블로그 초안을 생성하세요.</span>")
            elif (coupang_url or product_description) and not self.processor.gemini_model:
                self.signals.log_message.emit("<span style='color:orange;'>쿠팡 파트너스 URL 또는 상품 설명이 입력되었으나, Gemini 모델이 준비되지 않아 쿠팡 블로그 초안을 생성할 수 없습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.</span>")

        except InterruptedError:
            self.signals.log_message.emit("<span style='color:orange;'>작업이 중지되었습니다.</span>")
            self.signals.status_message.emit("중지됨")
            self.signals.progress.emit(0)
        except Exception as e:
            error_message = f"오류 발생: {e}"
            print(f"[DEBUG_GUI] _process_single_video_thread 에서 오류 발생: {error_message}")
            self.signals.log_message.emit(f"<span style='color:red;'>{error_message}</span>")
            self.signals.status_message.emit("오류 발생")
            self.signals.progress.emit(0)
        finally:
            if audio_path is not None and Path(audio_path).exists():
                try:
                    os.remove(audio_path)
                    self.signals.log_message.emit(f"임시 오디오 파일 삭제 완료: {audio_path}")
                except Exception as e:
                    self.signals.log_message.emit(f"임시 오디오 파일 삭제 실패: {e}")
            self.signals.finished.emit()

    def _process_local_video_for_transcript_thread(self, local_video_path):
        video_info = {'video_id': Path(local_video_path).stem, 'video_title': Path(local_video_path).stem, 'uploader': 'LocalVideo'}
        audio_path = None
        try:
            self.signals.log_message.emit("로컬 영상에서 오디오 추출 중...")
            self.signals.progress.emit(20)
            audio_path = self.processor.extract_audio(local_video_path)
            if audio_path is None:
                raise Exception("오디오 추출 실패.")

            self.signals.log_message.emit("대본 생성 중...")
            self.signals.progress.emit(70)
            transcript_text = self.processor.generate_transcript(audio_path)
            if transcript_text is None:
                raise Exception("대본 생성 실패: Whisper 모델이 텍스트를 반환하지 않았습니다.")
            print(f"[DEBUG_GUI] Whisper 대본 생성 결과 (로컬): {transcript_text[:50]}...")
            whisper_result = {"text": transcript_text, "segments": []}

            self.signals.log_message.emit("대본 저장 중...")
            print("[DEBUG_GUI] save_transcript 호출 전 (로컬).")
            transcript_success = self.processor.save_transcript(video_info, whisper_result)
            print(f"[DEBUG_GUI] save_transcript 호출 후 (로컬). 결과: {transcript_success}")
            if not transcript_success:
                raise Exception("대본 저장 실패.")

            self.signals.log_message.emit("콘텐츠 분석 중...")
            print("[DEBUG_GUI] analyze_video_content 호출 전 (로컬).")
            analysis_results = self.processor.analyze_video_content(video_info, whisper_result)
            print(f"[DEBUG_GUI] analyze_video_content 호출 후 (로컬). 결과: {analysis_results is not None}")
            if analysis_results is None:
                raise Exception("콘텐츠 분석 실패.")

            analysis_success = self.processor.save_analysis_results(video_info, analysis_results)
            print(f"[DEBUG_GUI] save_analysis_results 호출 후 (로컬). 결과: {analysis_success}")
            if not analysis_success:
                raise Exception("분석 결과 저장 실패.")

            tags_text = ", ".join(analysis_results.get('suggested_tags', []))
            self.signals.tags_output.emit(tags_text)
            self.signals.log_message.emit(f"\n<b>[태그 추출]</b>\n{tags_text}")

            content_ideas_list = analysis_results.get('content_ideas', [])
            content_ideas_text = "\n".join([f"- {idea}" for idea in content_ideas_list])
            self.signals.content_ideas_output.emit(content_ideas_text)
            self.signals.log_message.emit(f"\n<b>[콘텐츠 아이디어]</b>\n{content_ideas_text}")

            original_transcript_preview = transcript_text[:1000] + "..." if len(transcript_text) > 1000 else transcript_text
            self.signals.original_transcript_output.emit(original_transcript_preview)
            self.signals.log_message.emit(f"\n<b>[원본 대본 내용 (부분)]</b>\n{original_transcript_preview}")

            timestamped_summaries_list = analysis_results.get('timestamped_summaries', [])
            timestamped_summaries_text = ""
            for summary in timestamped_summaries_list:
                start_time = str(int(summary['start'] // 60)).zfill(2) + ":" + str(int(summary['start'] % 60)).zfill(2)
                end_time = str(int(summary['end'] // 60)).zfill(2) + ":" + str(int(summary['end'] % 60)).zfill(2)
                timestamped_summaries_text += f"[{start_time}-{end_time}] {summary['text']}\n"
            self.signals.timestamped_summaries_output.emit(timestamped_summaries_text)
            self.signals.log_message.emit(f"\n<b>[영상 핵심 요약 & 타임스탬프]</b>\n{timestamped_summaries_text}")

            self.signals.log_message.emit("로컬 영상 모든 작업 완료.")
            self.signals.status_message.emit("성공")
            self.signals.progress.emit(100)

            self.generate_blog_draft_btn.setEnabled(True)
            self.generate_coupang_blog_btn.setEnabled(True)
            self.export_results_btn.setEnabled(True)
            self.generate_platform_content_btn.setEnabled(True) # 플랫폼 최적화 버튼 활성화
            self.last_loaded_transcript_content = transcript_text
            self.last_loaded_video_title = video_info.get('video_title', '제목 없음')

        except InterruptedError:
            self.signals.log_message.emit("<span style='color:orange;'>로컬 영상 작업이 중지되었습니다.</span>")
            self.signals.status_message.emit("중지됨")
            self.signals.progress.emit(0)
        except Exception as e:
            error_message = f"로컬 영상 처리 중 오류 발생: {e}"
            print(f"[DEBUG_GUI] _process_local_video_for_transcript_thread 에서 오류 발생: {error_message}")
            self.signals.log_message.emit(f"<span style='color:red;'>{error_message}</span>")
            self.signals.status_message.emit("오류 발생")
            self.signals.progress.emit(0)
        finally:
            if audio_path and Path(audio_path).exists():
                try:
                    os.remove(audio_path)
                    self.signals.log_message.emit(f"임시 로컬 오디오 파일 삭제 완료: {audio_path}")
                except Exception as e:
                    self.signals.log_message.emit(f"임시 로컬 오디오 파일 삭제 실패: {e}")
            self.signals.finished.emit()

    def _process_profile_videos_thread(self, profile_url, coupang_url, product_description):
        """계정의 모든 영상 처리 스레드"""
        try:
            self.signals.log_message.emit(f"<b>계정({profile_url})의 모든 영상 다운로드 중...</b>")
            self.progress.setValue(0)
            self.signals.status_message.emit("계정 영상 목록 다운로드 중...")
            
            video_paths = self.processor.download_all_videos_from_profile_url(profile_url)
            
            if not video_paths:
                if self.stop_event.is_set():
                    self.signals.log_message.emit("<span style='color:orange;'>작업이 중지되었습니다.</span>")
                    self.signals.status_message.emit("중지됨")
                else:
                    self.signals.log_message.emit("<span style='color:red;'>계정에서 영상을 찾지 못했거나 다운로드 실패</span>")
                    self.signals.status_message.emit("실패: 영상 없음/다운로드 오류")
                return

            self.signals.log_message.emit(f"<b>총 {len(video_paths)}개의 영상 다운로드 완료. 대본 생성 시작...</b>")
            self.progress.setMaximum(len(video_paths))

            all_analysis_results = []
            all_suggested_tags = []
            all_content_ideas = []
            all_timestamped_summaries = []

            last_profile_video_transcript = ""

            for i, video_path in enumerate(video_paths, 1):
                if self.stop_event.is_set():
                    self.signals.log_message.emit("<span style='color:orange;'>작업이 사용자에 의해 중지되었습니다.</span>")
                    self.signals.status_message.emit("중지됨")
                    break

                self.signals.log_message.emit(f"\n<b>[{i}/{len(video_paths)}] 영상 처리 중: {Path(video_path).name}</b>")
                self.signals.status_message.emit(f"[{i}/{len(video_paths)}] 대본 생성 중...")
                
                audio_path = None
                try:
                    audio_path = self.processor.extract_audio(video_path)
                    if not audio_path:
                        if self.stop_event.is_set():
                            self.signals.log_message.emit("<span style='color:orange;'>작업이 중지되었습니다.</span>")
                            self.signals.status_message.emit("중지됨")
                            break
                        else:
                            self.signals.log_message.emit(f"<span style='color:orange;'>영상({Path(video_path).name}) 오디오 추출 실패 (건너뛰기)</span>")
                            continue

                    whisper_result = self.processor.generate_transcript(audio_path)
                    if whisper_result is None or "text" not in whisper_result:
                        raise Exception("대본 생성 실패: Whisper 모델이 텍스트를 반환하지 않았습니다.")
                    transcript_text = whisper_result["text"]
                    last_profile_video_transcript = transcript_text # 마지막 영상 대본 저장
                    print(f"[DEBUG_GUI] Whisper 대본 생성 결과: {transcript_text[:50]}...")

                    video_id = Path(video_path).stem
                    video_title = Path(video_path).name
                    uploader_name = Path(video_path).parent.name
                    
                    temp_video_info = {
                        'video_title': video_title,
                        'video_id': video_id,
                        'uploader': uploader_name,
                        'duration': None,
                        'url': 'Unknown_URL',
                        'downloaded_path': video_path
                    }

                    transcript_success = self.processor.save_transcript(temp_video_info, whisper_result)

                    if transcript_success:
                        self.signals.log_message.emit(f"<span style='color:green;'>영상({Path(video_path).name}) 대본 저장 완료. 콘텐츠 분석 중...</span>")
                        
                        analysis_results = self.processor.analyze_video_content(temp_video_info, whisper_result)
                        print(f"[DEBUG_GUI] analyze_video_content 결과: {analysis_results is not None}")
                        self.signals.log_message.emit("콘텐츠 분석 완료. 결과 저장 중...")
                        self.processor.save_analysis_results(temp_video_info, analysis_results)
                        
                        all_suggested_tags.extend(analysis_results.get('suggested_tags', []))
                        all_content_ideas.extend(analysis_results.get('content_ideas', []))
                        all_timestamped_summaries.extend(analysis_results.get('timestamped_summaries', []))

                    else:
                        self.signals.log_message.emit(f"<span style='color:orange;'>영상({Path(video_path).name}) 대본 저장 실패 (건너뛰기)</span>")

                except InterruptedError:
                    self.signals.log_message.emit("<b><span style='color:orange;'>작업이 사용자에 의해 중지되었습니다.</span></b>")
                    self.signals.status_message.emit("중지됨")
                    break
                except Exception as e:
                    self.signals.log_message.emit(f"<span style='color:red;'>영상({Path(video_path).name}) 처리 중 오류 발생: {e}</span>")
                finally:
                    if audio_path is not None and os.path.exists(audio_path):
                        try:
                            os.remove(audio_path)
                        except Exception as e:
                            self.signals.log_message.emit(f"<span style='color:orange;'>임시 오디오 파일 삭제 실패: {audio_path} - {e}</span>")

                self.progress.setValue(i)
            
            if not self.stop_event.is_set():
                self.signals.log_message.emit("<b>모든 계정 영상 처리가 완료되었습니다.</b>")
                self.signals.status_message.emit("성공")
                
                final_tags_text = ", ".join(list(set(all_suggested_tags)))
                print(f"[DEBUG_GUI] 최종 태그 텍스트: {final_tags_text}")
                self.signals.tags_output.emit(final_tags_text)
                self.signals.log_message.emit(f"\n<b>[최종 태그 추출 요약]</b>\n{final_tags_text}")

                final_content_ideas_text = "\n".join([f"- {idea}" for idea in list(set(all_content_ideas))])
                print(f"[DEBUG_GUI] 최종 콘텐츠 아이디어 텍스트: {final_content_ideas_text}")
                self.signals.content_ideas_output.emit(final_content_ideas_text)
                self.signals.log_message.emit(f"\n<b>[최종 콘텐츠 아이디어 요약]</b>\n{final_content_ideas_text}")

                final_timestamped_summaries_text = ""
                for summary in all_timestamped_summaries:
                    start_time = str(int(summary['start'] // 60)).zfill(2) + ":" + str(int(summary['start'] % 60)).zfill(2)
                    end_time = str(int(summary['end'] // 60)).zfill(2) + ":" + str(int(summary['end'] % 60)).zfill(2)
                    final_timestamped_summaries_text += f"[{start_time}-{end_time}] {summary['text']}\n"
                print(f"[DEBUG_GUI] 최종 타임스탬프 요약: {final_timestamped_summaries_text[:100]}...")
                self.signals.timestamped_summaries_output.emit(final_timestamped_summaries_text)
                self.signals.log_message.emit(f"\n<b>[최종 영상 핵심 요약 & 타임스탬프 요약]</b>\n{final_timestamped_summaries_text}")

                original_transcript_preview = last_profile_video_transcript[:1000] + "..." if len(last_profile_video_transcript) > 1000 else last_profile_video_transcript
                print(f"[DEBUG_GUI] 원본 대본 내용 (미리보기): {original_transcript_preview[:100]}...")
                self.signals.original_transcript_output.emit(original_transcript_preview)
                self.signals.log_message.emit(f"\n<b>[마지막 영상 원본 대본 내용 (부분)]</b>\n{original_transcript_preview}")

                self.generate_blog_draft_btn.setEnabled(True)
                self.generate_coupang_blog_btn.setEnabled(True)
                self.export_results_btn.setEnabled(True)
                self.generate_platform_content_btn.setEnabled(True) # 플랫폼 최적화 버튼 활성화
                self.last_loaded_transcript_content = last_profile_video_transcript
                self.last_loaded_video_title = "여러 영상 합본"

                # 쿠팡 파트너스 관련 데이터 저장 (초안 생성은 버튼 클릭 시)
                self.last_coupang_url = coupang_url
                self.last_product_description = product_description
                self.last_transcript_for_coupang = last_profile_video_transcript
                self.last_analysis_results_for_coupang = all_analysis_results # 분석 결과도 저장

                if coupang_url and not product_description:
                    self.signals.log_message.emit("<span style='color:blue;'>상품 설명이 비어있습니다. '쿠팡 블로그 초안 생성' 버튼 클릭 시, 분석된 영상 내용과 태그를 기반으로 상품 설명이 자동으로 생성됩니다.</span>")
                elif coupang_url and self.processor.gemini_model:
                    self.signals.log_message.emit("<span style='color:blue;'>쿠팡 파트너스 URL과 상품 설명이 입력되었습니다. '쿠팡 블로그 초안 생성' 버튼을 클릭하여 블로그 초안을 생성하세요.</span>")
                elif (coupang_url or product_description) and not self.processor.gemini_model:
                    self.signals.log_message.emit("<span style='color:orange;'>쿠팡 파트너스 URL 또는 상품 설명이 입력되었으나, Gemini 모델이 준비되지 않아 쿠팡 블로그 초안을 생성할 수 없습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.</span>")

        except InterruptedError:
            self.signals.log_message.emit("<b><span style='color:orange;'>작업이 사용자에 의해 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>계정 영상 처리 중 치명적인 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    def _process_channel_with_filters_thread(self, channel_url, min_views, video_type, keywords, coupang_url, product_description):
        """채널 URL을 받아서 필터링 조건에 맞는 동영상들을 처리하는 스레드"""
        try:
            self.signals.log_message.emit(f"<b>채널 필터링 처리 시작: {channel_url}</b>")
            self.signals.log_message.emit(f"<b>필터 조건: 최소 조회수={min_views}, 유형={video_type}, 키워드={keywords}</b>")
            self.progress.setValue(0)
            self.signals.status_message.emit("채널 동영상 필터링 중...")
            
            # 1단계: 필터링된 동영상 목록 가져오기
            filtered_videos = self.processor.get_channel_videos_with_filters(channel_url, min_views, video_type, keywords)
            
            if not filtered_videos:
                if self.stop_event.is_set():
                    self.signals.log_message.emit("<span style='color:orange;'>작업이 중지되었습니다.</span>")
                    self.signals.status_message.emit("중지됨")
                else:
                    self.signals.log_message.emit("<span style='color:red;'>조건에 맞는 동영상을 찾지 못했습니다.</span>")
                    self.signals.status_message.emit("실패: 조건에 맞는 동영상 없음")
                return

            self.signals.log_message.emit(f"<b>필터링 완료: {len(filtered_videos)}개의 동영상 선택됨</b>")
            
            # 2단계: 필터링된 동영상들 다운로드
            self.signals.status_message.emit("선택된 동영상 다운로드 중...")
            downloaded_videos = self.processor.download_filtered_videos(filtered_videos)
            
            if not downloaded_videos:
                self.signals.log_message.emit("<span style='color:red;'>동영상 다운로드에 실패했습니다.</span>")
                self.signals.status_message.emit("실패: 다운로드 오류")
                return

            self.signals.log_message.emit(f"<b>총 {len(downloaded_videos)}개의 동영상 다운로드 완료. 분석 시작...</b>")
            self.progress.setMaximum(len(downloaded_videos))

            all_analysis_results = []
            all_suggested_tags = []
            all_content_ideas = []
            all_timestamped_summaries = []
            last_video_transcript = ""

            # 3단계: 각 동영상에 대해 분석 수행
            for i, video_info in enumerate(downloaded_videos, 1):
                if self.stop_event.is_set():
                    self.signals.log_message.emit("<span style='color:orange;'>작업이 사용자에 의해 중지되었습니다.</span>")
                    self.signals.status_message.emit("중지됨")
                    break

                video_title = video_info.get('video_title', 'Unknown')
                self.signals.log_message.emit(f"\n<b>[{i}/{len(downloaded_videos)}] 동영상 분석 중: {video_title}</b>")
                self.signals.status_message.emit(f"[{i}/{len(downloaded_videos)}] 분석 중...")
                
                audio_path = None
                try:
                    video_path = video_info.get('downloaded_path')
                    if not video_path or not os.path.exists(video_path):
                        self.signals.log_message.emit(f"<span style='color:orange;'>동영상 파일을 찾을 수 없습니다: {video_title}</span>")
                        continue

                    audio_path = self.processor.extract_audio(video_path)
                    if not audio_path:
                        if self.stop_event.is_set():
                            self.signals.log_message.emit("<span style='color:orange;'>작업이 중지되었습니다.</span>")
                            self.signals.status_message.emit("중지됨")
                            break
                        else:
                            self.signals.log_message.emit(f"<span style='color:orange;'>동영상({video_title}) 오디오 추출 실패 (건너뛰기)</span>")
                            continue

                    transcript = self.processor.generate_transcript(audio_path)
                    if transcript:
                        last_video_transcript = transcript
                        
                        # 대본 저장
                        self.processor.save_transcript(video_info, {"text": transcript})
                        
                        # 콘텐츠 분석
                        analysis_results = self.processor.analyze_video_content(video_info, {"text": transcript})
                        if analysis_results:
                            self.processor.save_analysis_results(video_info, analysis_results)
                            
                            all_suggested_tags.extend(analysis_results.get('suggested_tags', []))
                            all_content_ideas.extend(analysis_results.get('content_ideas', []))
                            all_timestamped_summaries.extend(analysis_results.get('timestamped_summaries', []))
                            
                            self.signals.log_message.emit(f"<span style='color:green;'>동영상({video_title}) 분석 완료</span>")
                        else:
                            self.signals.log_message.emit(f"<span style='color:orange;'>동영상({video_title}) 분석 실패 (건너뛰기)</span>")
                    else:
                        self.signals.log_message.emit(f"<span style='color:orange;'>동영상({video_title}) 대본 생성 실패 (건너뛰기)</span>")

                except InterruptedError:
                    self.signals.log_message.emit("<b><span style='color:orange;'>작업이 사용자에 의해 중지되었습니다.</span></b>")
                    self.signals.status_message.emit("중지됨")
                    break
                except Exception as e:
                    self.signals.log_message.emit(f"<span style='color:red;'>동영상({video_title}) 처리 중 오류 발생: {e}</span>")
                finally:
                    if audio_path is not None and os.path.exists(audio_path):
                        try:
                            os.remove(audio_path)
                        except Exception as e:
                            self.signals.log_message.emit(f"<span style='color:orange;'>임시 오디오 파일 삭제 실패: {audio_path} - {e}</span>")

                self.progress.setValue(i)
            
            if not self.stop_event.is_set():
                self.signals.log_message.emit("<b>채널 필터링 처리가 완료되었습니다.</b>")
                self.signals.status_message.emit("성공")
                
                # 결과 출력
                final_tags_text = ", ".join(list(set(all_suggested_tags)))
                self.signals.tags_output.emit(final_tags_text)
                self.signals.log_message.emit(f"\n<b>[최종 태그 추출 요약]</b>\n{final_tags_text}")

                final_content_ideas_text = "\n".join([f"- {idea}" for idea in list(set(all_content_ideas))])
                self.signals.content_ideas_output.emit(final_content_ideas_text)
                self.signals.log_message.emit(f"\n<b>[최종 콘텐츠 아이디어 요약]</b>\n{final_content_ideas_text}")

                final_timestamped_summaries_text = ""
                for summary in all_timestamped_summaries:
                    start_time = str(int(summary['start'] // 60)).zfill(2) + ":" + str(int(summary['start'] % 60)).zfill(2)
                    end_time = str(int(summary['end'] // 60)).zfill(2) + ":" + str(int(summary['end'] % 60)).zfill(2)
                    final_timestamped_summaries_text += f"[{start_time}-{end_time}] {summary['text']}\n"
                self.signals.timestamped_summaries_output.emit(final_timestamped_summaries_text)
                self.signals.log_message.emit(f"\n<b>[최종 영상 핵심 요약 & 타임스탬프 요약]</b>\n{final_timestamped_summaries_text}")

                original_transcript_preview = last_video_transcript[:1000] + "..." if len(last_video_transcript) > 1000 else last_video_transcript
                self.signals.original_transcript_output.emit(original_transcript_preview)
                self.signals.log_message.emit(f"\n<b>[마지막 동영상 원본 대본 내용 (부분)]</b>\n{original_transcript_preview}")

                # 버튼 활성화
                self.generate_blog_draft_btn.setEnabled(True)
                self.generate_coupang_blog_btn.setEnabled(True)
                self.export_results_btn.setEnabled(True)
                self.generate_platform_content_btn.setEnabled(True)
                
                # 데이터 저장
                self.last_loaded_transcript_content = last_video_transcript
                self.last_loaded_video_title = "필터링된 채널 동영상들"
                self.last_coupang_url = coupang_url
                self.last_product_description = product_description
                self.last_transcript_for_coupang = last_video_transcript

        except InterruptedError:
            self.signals.log_message.emit("<b><span style='color:orange;'>작업이 사용자에 의해 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>채널 필터링 처리 중 치명적인 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    def generate_blog_draft_action(self):
        """블로그 초안 생성 버튼 클릭 시 호출되는 함수"""
        if not hasattr(self, 'last_loaded_transcript_content') or not self.last_loaded_transcript_content:
            QMessageBox.warning(self, "경고", "먼저 영상을 분석하거나 이전 분석 결과를 로드하여 대본을 준비해주세요.")
            return

        if self.processor and self.processor.gemini_model:
            self.signals.log_message.emit("<b>\n블로그 초안 생성 시작 (Gemini API 사용)...</b>")
            self.blog_draft_output.clear()
            self.generate_blog_draft_btn.setEnabled(False)
            self.status_label.setText("블로그 초안 생성 중...")

            self.current_thread = threading.Thread(target=self._generate_blog_draft_thread, 
                                                    args=(self.last_loaded_video_title, self.last_loaded_transcript_content,),
                                                    daemon=True)
            self.current_thread.start()
        else:
            QMessageBox.warning(self, "경고", "Gemini API가 설정되지 않았거나 모델이 로드되지 않았습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.")
            self.signals.log_message.emit("<span style='color:red;'>Gemini API가 설정되지 않아 블로그 초안을 생성할 수 없습니다.</span>")

    def _generate_blog_draft_thread(self, video_title, transcript_content):
        """블로그 초안 생성 스레드"""
        try:
            self.signals.progress.emit(10)
            prompt = f"""'{video_title}' 영상 대본을 바탕으로 네이버 블로그 게시물 초안을 작성해주세요. 다음 사항을 포함해주세요:

1. **제목**: 영상 내용을 잘 나타내는 매력적인 제목
2. **소개**: 영상의 주요 내용과 흥미를 유발하는 도입부
3. **본론 (3~5개 소제목)**: 영상의 핵심 내용과 타임스탬프 요약을 활용하여 구체적인 정보를 제공
4. **결론**: 요약 및 시청자에게 행동 유도 (예: '구독하기', '댓글 달기')
5. **추천 태그**: 블로그에 사용할 관련 태그 (5개 이상)

대본 내용:
{transcript_content[:4000]}...

"""

            response = self.processor.gemini_model.generate_content(prompt)

            if response.candidates:
                blog_draft_text = response.candidates[0].content.parts[0].text
                print(f"[DEBUG_GUI] 블로그 초안 텍스트: {blog_draft_text[:100]}...")
                self.signals.blog_draft_output.emit(blog_draft_text)
                self.signals.log_message.emit("<b>\n블로그 초안 생성 완료!</b>")
                self.signals.status_message.emit("블로그 초안 생성 완료")
                self.signals.progress.emit(100)
            else:
                self.signals.log_message.emit("<span style='color:orange;'>블로그 초안 생성에 실패했습니다.</span>")
                self.signals.status_message.emit("실패: 초안 생성 오류")

        except InterruptedError:
            self.signals.log_message.emit("<b><span style='color:orange;'>블로그 초안 생성 작업이 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>블로그 초안 생성 중 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    def generate_coupang_blog_action(self):
        """쿠팡 블로그 초안 생성 버튼 클릭 시 호출되는 함수"""
        if not hasattr(self, 'last_coupang_url') or not self.last_coupang_url:
            QMessageBox.warning(self, "경고", "쿠팡 파트너스 상품 URL이 입력되지 않았습니다. 먼저 영상을 분석하거나 이전 분석 결과를 로드해주세요.")
            return

        if not self.processor or not self.processor.gemini_model:
            QMessageBox.warning(self, "경고", "Gemini API가 설정되지 않았거나 모델이 로드되지 않았습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.")
            self.signals.log_message.emit("<span style='color:red;'>Gemini API가 설정되지 않아 쿠팡 블로그 초안을 생성할 수 없습니다.</span>")
            return

        # 상품 설명이 비어있으면 자동 생성 로직 실행
        product_description_to_use = self.last_product_description
        if not product_description_to_use and hasattr(self, 'last_analysis_results_for_coupang') and self.last_analysis_results_for_coupang and self.last_transcript_for_coupang:
            self.signals.log_message.emit("<b>\n상품 설명 자동 생성 시작...</b>")
            generated_description = self.processor.generate_product_description_from_analysis(
                self.last_transcript_for_coupang,
                self.last_analysis_results_for_coupang.get('suggested_tags', []),
                self.last_analysis_results_for_coupang.get('content_ideas', []),
                self.last_analysis_results_for_coupang.get('timestamped_summaries', [])
            )
            if generated_description:
                product_description_to_use = generated_description
                self.last_product_description = generated_description # 자동 생성된 상품 설명을 클래스 변수에 저장
                self.signals.log_message.emit("<b>상품 설명 자동 생성 완료.</b>")
            else:
                self.signals.log_message.emit("<span style='color:orange;'>상품 설명 자동 생성에 실패했습니다.</span>")
                QMessageBox.warning(self, "오류", "상품 설명을 자동으로 생성할 수 없습니다. 수동으로 입력하거나 다시 시도해주세요.")
                return

        if not product_description_to_use:
             QMessageBox.warning(self, "경고", "상품 설명이 없습니다. 수동으로 입력하거나 다시 시도해주세요.")
             return

        manual_image_url = self.image_url_input.text().strip() # 수동 이미지 URL 가져오기

        self.signals.log_message.emit("<b>\n쿠팡 블로그 초안 생성 시작 (Gemini API 사용)...</b>")
        self.coupang_blog_output.clear()
        self.generate_coupang_blog_btn.setEnabled(False)
        self.status_label.setText("쿠팡 블로그 초안 생성 중...")

        self.current_thread = threading.Thread(target=self._generate_coupang_blog_thread,
                                                args=(self.last_coupang_url, product_description_to_use, self.last_transcript_for_coupang, manual_image_url,),
                                                daemon=True)
        self.current_thread.start()

    def _generate_coupang_blog_thread(self, coupang_url, product_description, transcript_content, manual_image_url):
        """쿠팡 블로그 초안 생성 스레드"""
        try:
            self.signals.progress.emit(10)
            generated_coupang_blog = self.processor.generate_coupang_blog_draft(
                coupang_url,
                product_description,
                transcript_content,
                manual_image_url # 수동 이미지 URL 전달
            )
            
            if generated_coupang_blog:
                self.signals.coupang_blog_output.emit(generated_coupang_blog)
                self.signals.log_message.emit("<b>\n쿠팡 블로그 초안 생성 완료!</b>")
                self.signals.status_message.emit("쿠팡 블로그 초안 생성 완료")
                self.signals.progress.emit(100)
            else:
                self.signals.log_message.emit("<span style='color:orange;'>쿠팡 블로그 초안 생성에 실패했습니다.</span>")
                self.signals.status_message.emit("실패: 초안 생성 오류")

        except InterruptedError:
            self.signals.log_message.emit("<b><span style='color:orange;'>쿠팡 블로그 초안 생성 작업이 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>쿠팡 블로그 초안 생성 중 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    def on_process_finished(self):
        self.process_btn.setEnabled(True)
        self.channel_filter_btn.setEnabled(True)  # 채널 필터링 버튼 다시 활성화
        self.stop_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(True)
        self.local_transcribe_btn.setEnabled(True)
        if hasattr(self, 'last_loaded_transcript_content') and self.last_loaded_transcript_content:
            self.generate_blog_draft_btn.setEnabled(True)
            self.generate_coupang_blog_btn.setEnabled(True)
            self.export_results_btn.setEnabled(True)
            self.generate_platform_content_btn.setEnabled(True) # 플랫폼 최적화 버튼 활성화
            # 숏츠 제작 관련 버튼들 활성화
            self.generate_shorts_script_btn.setEnabled(True)
            self.generate_shorts_hook_btn.setEnabled(True)
            self.generate_shorts_hashtags_btn.setEnabled(True)
            self.generate_shorts_timeline_btn.setEnabled(True)
            self.generate_shorts_ab_test_btn.setEnabled(True)
            self.export_shorts_results_btn.setEnabled(True)  # 숏츠 제작 결과 내보내기 버튼 활성화

        # 쿠팡 블로그 초안 생성 버튼 활성화 조건
        if hasattr(self, 'last_coupang_url') and self.last_coupang_url and \
           hasattr(self, 'last_transcript_for_coupang') and self.last_transcript_for_coupang:
            self.generate_coupang_blog_btn.setEnabled(True)

        # AI 콘텐츠 생성 버튼은 제품 특징/장점 입력 필드가 비어있지 않을 때만 활성화
        # if self.product_features_input.toPlainText().strip():
        #     self.generate_script_btn.setEnabled(True)

    def export_all_results_action(self):
        """현재 UI에 표시된 모든 분석 결과를 통합하여 텍스트 파일로 저장하고, ChatGPT 프롬프트를 생성합니다."""
        tags = self.tags_output.toPlainText()
        content_ideas = self.content_ideas_output.toPlainText()
        original_transcript = self.original_transcript_output.toPlainText()
        timestamped_summaries = self.timestamped_summaries_output.toPlainText()
        blog_draft = self.blog_draft_output.toPlainText()
        coupang_blog_draft = self.coupang_blog_output.toPlainText() # 쿠팡 블로그 초안도 포함

        if not (tags or content_ideas or original_transcript or timestamped_summaries or blog_draft or coupang_blog_draft):
            QMessageBox.warning(self, "내보내기 오류", "내보낼 분석 결과가 없습니다.")
            return

        combined_content = ""
        if tags: combined_content += f"태그 추출:\n{tags}\n\n"
        if content_ideas: combined_content += f"콘텐츠 아이디어:\n{content_ideas}\n\n"
        if original_transcript: combined_content += f"원본 대본 내용:\n{original_transcript}\n\n"
        if timestamped_summaries: combined_content += f"영상 핵심 요약 & 타임스탬프:\n{timestamped_summaries}\n\n"
        if blog_draft: combined_content += f"블로그 초안:\n{blog_draft}\n\n"
        if coupang_blog_draft: combined_content += f"쿠팡 파트너스 블로그 초안:\n{coupang_blog_draft}\n\n"

        gpt_data_folder = Path("GPT_data")
        gpt_data_folder.mkdir(parents=True, exist_ok=True)

        default_file_name = "analysis_results"
        if blog_draft:
            first_line = blog_draft.split('\n')[0].strip()
            if first_line:
                default_file_name = first_line
        elif hasattr(self, 'last_loaded_video_title') and self.last_loaded_video_title:
            default_file_name = self.last_loaded_video_title

        default_file_name = re.sub(r'[\\/:*?"<>|]', '', default_file_name)
        default_file_name = f"{default_file_name}.txt"

        file_name, _ = QFileDialog.getSaveFileName(self, "분석 결과 저장", str(gpt_data_folder / default_file_name), "텍스트 파일 (*.txt);;모든 파일 (*)")

        if file_name:
            try:
                with open(file_name, 'w', encoding='utf-8') as f:
                    f.write(combined_content)
                QMessageBox.information(self, "저장 성공", f"분석 결과가 다음 위치에 저장되었습니다:\n{file_name}")

                chatgpt_prompt = f"""
다음은 영상 분석 결과입니다. 이 자료를 바탕으로 SEO에 최적화된 블로그 게시물을 작성해주세요.

--- 영상 분석 결과 ---
{combined_content}
---

블로그 게시물은 다음 요소를 포함해야 합니다:
1. 매력적인 제목 (SEO 키워드 포함)
2. 도입부: 영상 내용 요약 및 주제 소개
3. 본문: 주요 내용과 타임스탬프 요약을 바탕으로 상세 설명
4. 콘텐츠 아이디어를 활용하여 추가적인 가치 제공
5. 결론: 요약 및 마무리
6. 관련 태그를 활용한 자연스러운 키워드 통합

블로그 글의 톤앤매너는 전문적이면서도 친근하게 유지하고, 독자들이 쉽게 이해하고 흥미를 느낄 수 있도록 작성해주세요.
"""

                QMessageBox.information(self, "ChatGPT 프롬프트", chatgpt_prompt)

            except Exception as e:
                QMessageBox.critical(self.parent(), "저장 오류", f"파일 저장 중 오류가 발생했습니다:\n{e}")

    def generate_product_script_action(self):
        """제품 영상 스크립트/후크 생성 버튼 클릭 시 호출되는 함수"""
        product_features = self.product_features_input.toPlainText().strip()
        target_audience = self.target_audience_input.text().strip()
        video_purpose = self.video_purpose_combo.currentText()

        if not product_features:
            QMessageBox.warning(self, "입력 오류", "제품 특징/장점을 입력해주세요.")
            return
        
        if self.processor and self.processor.gemini_model:
            self.signals.log_message.emit("<b>\n제품 영상 스크립트/후크 생성 시작 (Gemini API 사용)...</b>")
            # self.script_output.clear() # 제거된 스크립트 출력 필드 초기화 제거
            self.generate_script_btn.setEnabled(False)
            self.status_label.setText("스크립트/후크 생성 중...")

            self.current_thread = threading.Thread(target=self._generate_product_script_thread, 
                                                    args=(product_features, target_audience, video_purpose,),
                                                    daemon=True)
            self.current_thread.start()
        else:
            QMessageBox.warning(self, "경고", "Gemini API가 설정되지 않았거나 모델이 로드되지 않았습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.")
            self.signals.log_message.emit("<span style='color:red;'>Gemini API가 설정되지 않아 스크립트/후크를 생성할 수 없습니다.</span>")

    def _generate_product_script_thread(self, product_features, target_audience, video_purpose):
        """제품 영상 스크립트/후크 생성 스레드"""
        try:
            self.signals.progress.emit(10)
            generated_script = self.processor.generate_product_script(product_features, target_audience, video_purpose)
            
            if generated_script:
                print(f"[DEBUG_GUI] 생성된 스크립트: {generated_script[:100]}...")
                # self.signals.script_output.emit(generated_script) # 제거된 스크립트 출력 필드에 해당하는 시그널 제거
                self.signals.log_message.emit("<b>\n제품 영상 스크립트/후크 생성 완료!</b>")
                self.signals.status_message.emit("스크립트/후크 생성 완료")
                self.signals.progress.emit(100)
            else:
                self.signals.log_message.emit("<span style='color:orange;'>스크립트/후크 생성에 실패했습니다.</span>")
                self.signals.status_message.emit("실패: 초안 생성 오류")

        except InterruptedError:
            self.signals.log_message.emit("<b><span style='color:orange;'>스크립트 생성 작업이 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>스크립트 생성 중 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    def generate_platform_optimized_content_action(self):
        """
        플랫폼 최적화 콘텐츠 생성 버튼 클릭 시 호출되는 함수
        """
        platform_type = self.platform_combobox.currentText()
        product_url = self.coupang_url_input.text().strip()
        product_description = self.product_description_input.toPlainText().strip()
        transcript_content = self.last_loaded_transcript_content if hasattr(self, 'last_loaded_transcript_content') else ""

        if not transcript_content:
            QMessageBox.warning(self, "입력 오류", "먼저 영상 대본을 로드하거나 생성해야 합니다.")
            return

        if not product_url:
            QMessageBox.warning(self, "입력 오류", "쿠팡 파트너스 상품 URL을 입력해야 합니다.")
            return
        
        # 상품 설명이 비어있으면 경고 (선택 사항이지만 콘텐츠 품질을 위해 필요)
        if not product_description:
            reply = QMessageBox.question(self, "경고", "상품 설명이 비어있습니다. 이대로 진행하시겠습니까? (콘텐츠 품질에 영향이 있을 수 있습니다.)",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return

        if self.processor and self.processor.gemini_model:
            self.signals.log_message.emit(f"<b>\n{platform_type} 콘텐츠 생성 시작 (Gemini API 사용)...</b>")
            self.platform_content_output.clear()
            self.generate_platform_content_btn.setEnabled(False)
            self.status_label.setText(f"{platform_type} 콘텐츠 생성 중...")

            self.current_thread = threading.Thread(target=self._generate_platform_optimized_content_thread, 
                                                    args=(platform_type, product_url, product_description, transcript_content,),
                                                    daemon=True)
            self.current_thread.start()
        else:
            QMessageBox.warning(self, "경고", "Gemini API가 설정되지 않았거나 모델이 로드되지 않았습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.")
            self.signals.log_message.emit("<span style='color:red;'>Gemini API가 설정되지 않아 콘텐츠를 생성할 수 없습니다.</span>")

    def _generate_platform_optimized_content_thread(self, platform_type, product_url, product_description, transcript_content):
        """플랫폼 최적화 콘텐츠 생성 스레드"""
        try:
            self.signals.progress.emit(10)
            generated_content = self.processor.generate_platform_optimized_content(
                platform_type,
                product_url,
                product_description,
                transcript_content
            )
            
            if generated_content:
                print(f"[DEBUG_GUI] 생성된 {platform_type} 콘텐츠: {generated_content[:100]}...")
                self.signals.platform_content_output.emit(generated_content)
                self.signals.log_message.emit(f"<b>\n{platform_type} 콘텐츠 생성 완료!</b>")
                self.signals.status_message.emit(f"{platform_type} 콘텐츠 생성 완료")
                self.signals.progress.emit(100)
            else:
                self.signals.log_message.emit(f"<span style='color:orange;'>{platform_type} 콘텐츠 생성에 실패했습니다.</span>")
                self.signals.status_message.emit(f"실패: {platform_type} 콘텐츠 생성 오류")

        except InterruptedError:
            self.signals.log_message.emit(f"<b><span style='color:orange;'>{platform_type} 콘텐츠 생성 작업이 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>{platform_type} 콘텐츠 생성 중 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    def safe_update_ui(self):
        # 여기에 UI 업데이트 로직을 추가할 수 있습니다.
        pass

    def start_channel_filtering_only(self):
        """채널 필터링만 실행하여 조건에 맞는 영상 URL 목록을 제공"""
        url = self.url_input.text().strip()
        google_api_key = self.google_api_key_input.text().strip()
        
        # 필터링 옵션 가져오기
        min_views_text = self.min_views_input.text().strip()
        min_views = int(min_views_text) if min_views_text.isdigit() else None
        video_type = self.video_type_combo.currentText()
        if video_type == "전체":
            video_type = None
        keywords = self.keywords_input.text().strip() if self.keywords_input.text().strip() else None

        if not url:
            QMessageBox.warning(self, "입력 오류", "채널 URL을 입력해주세요.")
            return
        
        if not google_api_key:
            QMessageBox.warning(self, "입력 오류", "Google API Key를 입력해주세요.")
            return

        # 채널 URL인지 확인
        is_channel_url = re.match(r'^https?://(www\.)?youtube\.com/(channel|user|c)/[\w.-]+/?', url) or \
                        re.match(r'^https?://(www\.)?youtube\.com/@[\w.-]+/?', url)
        
        if not is_channel_url:
            QMessageBox.warning(self, "입력 오류", "YouTube 채널 URL을 입력해주세요.")
            return

        if not (min_views or video_type or keywords):
            QMessageBox.warning(self, "입력 오류", "최소 하나의 필터링 조건을 설정해주세요.")
            return
        
        self.signals.log_message.emit(f"<b>\n채널 필터링만 실행 시작: {url}</b>")
        self.signals.log_message.emit(f"<b>필터 조건: 최소 조회수={min_views}, 유형={video_type}, 키워드={keywords}</b>")
        
        self.progress.setValue(0)
        self.status_label.setText("채널 필터링 중...")
        self.tags_output.clear()
        self.content_ideas_output.clear()
        self.original_transcript_output.clear()
        self.timestamped_summaries_output.clear()
        self.blog_draft_output.clear()
        self.coupang_blog_output.clear()

        self.process_btn.setEnabled(False)
        self.channel_filter_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(False)
        self.local_transcribe_btn.setEnabled(False)
        self.generate_blog_draft_btn.setEnabled(False)
        self.export_results_btn.setEnabled(False)

        self.stop_event.clear()

        self.processor = VideoProcessor(stop_event=self.stop_event, api_key=google_api_key)

        # 채널 필터링만 실행하는 스레드 시작
        self.current_thread = threading.Thread(
            target=self._process_channel_filtering_only_thread, 
            args=(url, min_views, video_type, keywords,), 
            daemon=True
        )
        self.current_thread.start()

    def _process_channel_filtering_only_thread(self, channel_url, min_views, video_type, keywords):
        """채널 필터링만 실행하여 조건에 맞는 영상 URL 목록을 제공하는 스레드"""
        try:
            self.signals.log_message.emit(f"<b>채널 필터링 시작: {channel_url}</b>")
            self.signals.log_message.emit(f"<b>필터 조건: 최소 조회수={min_views}, 유형={video_type}, 키워드={keywords}</b>")
            self.progress.setValue(0)
            self.signals.status_message.emit("채널 동영상 필터링 중...")
            
            # 필터링된 동영상 목록 가져오기
            filtered_videos = self.processor.get_channel_videos_with_filters(channel_url, min_views, video_type, keywords)
            
            if not filtered_videos:
                if self.stop_event.is_set():
                    self.signals.log_message.emit("<span style='color:orange;'>작업이 중지되었습니다.</span>")
                    self.signals.status_message.emit("중지됨")
                else:
                    self.signals.log_message.emit("<span style='color:red;'>조건에 맞는 동영상을 찾지 못했습니다.</span>")
                    self.signals.status_message.emit("실패: 조건에 맞는 동영상 없음")
                return

            self.signals.log_message.emit(f"<b>필터링 완료: {len(filtered_videos)}개의 동영상 선택됨</b>")
            
            # 필터링된 동영상들의 정보 출력
            video_urls = []
            for i, video_info in enumerate(filtered_videos, 1):
                video_title = video_info.get('title', 'Unknown')
                video_url = video_info.get('webpage_url') or video_info.get('url')
                view_count = video_info.get('view_count', 0)
                duration = video_info.get('duration', 0)
                
                if video_url:
                    video_urls.append(video_url)
                
                self.signals.log_message.emit(f"<b>[{i}] {video_title}</b>")
                self.signals.log_message.emit(f"URL: {video_url}")
                self.signals.log_message.emit(f"조회수: {view_count:,} | 길이: {duration}초")
                self.signals.log_message.emit("---")

            # URL 목록을 태그 출력란에 표시
            urls_text = "\n".join([f"{i+1}. {url}" for i, url in enumerate(video_urls)])
            self.signals.tags_output.emit(f"<b>필터링된 영상 URL 목록:</b>\n{urls_text}")
            
            # 원본 대본 출력란에 URL들을 쉼표로 구분하여 표시 (복사용)
            urls_for_copy = ", ".join(video_urls)
            self.signals.original_transcript_output.emit(f"<b>복사용 URL 목록:</b>\n{urls_for_copy}")
            
            # 콘텐츠 아이디어 출력란에 요약 정보 표시
            summary_text = f"총 {len(filtered_videos)}개 영상이 조건에 맞습니다.\n\n"
            summary_text += f"필터 조건:\n"
            summary_text += f"- 최소 조회수: {min_views or '제한없음'}\n"
            summary_text += f"- 동영상 유형: {video_type or '전체'}\n"
            summary_text += f"- 키워드: {keywords or '제한없음'}\n\n"
            summary_text += "위 URL들을 복사하여 'URL 다운로드 및 대본 생성' 기능에서 개별 분석하세요."
            self.signals.content_ideas_output.emit(summary_text)
            
            self.signals.log_message.emit(f"<b>채널 필터링 완료!</b>")
            self.signals.log_message.emit(f"<b>총 {len(filtered_videos)}개의 영상 URL을 제공받았습니다.</b>")
            self.signals.log_message.emit(f"<b>위 URL들을 복사하여 'URL 다운로드 및 대본 생성' 기능에서 개별 분석하세요.</b>")
            self.signals.status_message.emit("채널 필터링 완료")

        except InterruptedError:
            self.signals.log_message.emit("<b><span style='color:orange;'>작업이 사용자에 의해 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>채널 필터링 중 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    # 숏츠 제작 관련 함수들
    def generate_shorts_script_action(self):
        """숏츠 스크립트 생성 버튼 클릭 시 호출되는 함수"""
        transcript_content = self.last_loaded_transcript_content if hasattr(self, 'last_loaded_transcript_content') else ""
        
        if not transcript_content:
            QMessageBox.warning(self, "입력 오류", "먼저 영상 대본을 로드하거나 생성해야 합니다.")
            return

        video_length = self.shorts_length_combo.currentText()
        platform = self.shorts_platform_combo.currentText()
        content_type = self.shorts_type_combo.currentText()

        if self.processor and self.processor.gemini_model:
            self.signals.log_message.emit(f"<b>\n숏츠 스크립트 생성 시작 ({video_length}, {platform})...</b>")
            self.shorts_script_output.clear()
            self.generate_shorts_script_btn.setEnabled(False)
            self.status_label.setText("숏츠 스크립트 생성 중...")

            self.current_thread = threading.Thread(
                target=self._generate_shorts_script_thread, 
                args=(transcript_content, video_length, platform, content_type,),
                daemon=True
            )
            self.current_thread.start()
        else:
            QMessageBox.warning(self, "경고", "Gemini API가 설정되지 않았거나 모델이 로드되지 않았습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.")
            self.signals.log_message.emit("<span style='color:red;'>Gemini API가 설정되지 않아 스크립트를 생성할 수 없습니다.</span>")

    def _generate_shorts_script_thread(self, transcript_content, video_length, platform, content_type):
        """숏츠 스크립트 생성 스레드"""
        try:
            self.signals.progress.emit(10)
            generated_script = self.processor.generate_shorts_script(transcript_content, video_length, platform, content_type)
            
            if generated_script:
                print(f"[DEBUG_GUI] 생성된 숏츠 스크립트: {generated_script[:100]}...")
                self.signals.shorts_script_output.emit(generated_script)
                self.signals.log_message.emit("<b>\n숏츠 스크립트 생성 완료!</b>")
                self.signals.status_message.emit("숏츠 스크립트 생성 완료")
                self.signals.progress.emit(100)
            else:
                self.signals.log_message.emit("<span style='color:orange;'>숏츠 스크립트 생성에 실패했습니다.</span>")
                self.signals.status_message.emit("실패: 스크립트 생성 오류")

        except InterruptedError:
            self.signals.log_message.emit("<b><span style='color:orange;'>숏츠 스크립트 생성 작업이 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>숏츠 스크립트 생성 중 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    def generate_shorts_hook_action(self):
        """숏츠 후크 생성 버튼 클릭 시 호출되는 함수"""
        transcript_content = self.last_loaded_transcript_content if hasattr(self, 'last_loaded_transcript_content') else ""
        
        if not transcript_content:
            QMessageBox.warning(self, "입력 오류", "먼저 영상 대본을 로드하거나 생성해야 합니다.")
            return

        platform = self.shorts_platform_combo.currentText()
        content_type = self.shorts_type_combo.currentText()

        if self.processor and self.processor.gemini_model:
            self.signals.log_message.emit(f"<b>\n숏츠 후크 생성 시작 ({platform})...</b>")
            self.shorts_hook_output.clear()
            self.generate_shorts_hook_btn.setEnabled(False)
            self.status_label.setText("숏츠 후크 생성 중...")

            self.current_thread = threading.Thread(
                target=self._generate_shorts_hook_thread, 
                args=(transcript_content, platform, content_type,),
                daemon=True
            )
            self.current_thread.start()
        else:
            QMessageBox.warning(self, "경고", "Gemini API가 설정되지 않았거나 모델이 로드되지 않았습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.")
            self.signals.log_message.emit("<span style='color:red;'>Gemini API가 설정되지 않아 후크를 생성할 수 없습니다.</span>")

    def _generate_shorts_hook_thread(self, transcript_content, platform, content_type):
        """숏츠 후크 생성 스레드"""
        try:
            self.signals.progress.emit(10)
            generated_hook = self.processor.generate_shorts_hook(transcript_content, platform, content_type)
            
            if generated_hook:
                print(f"[DEBUG_GUI] 생성된 숏츠 후크: {generated_hook[:100]}...")
                self.signals.shorts_hook_output.emit(generated_hook)
                self.signals.log_message.emit("<b>\n숏츠 후크 생성 완료!</b>")
                self.signals.status_message.emit("숏츠 후크 생성 완료")
                self.signals.progress.emit(100)
            else:
                self.signals.log_message.emit("<span style='color:orange;'>숏츠 후크 생성에 실패했습니다.</span>")
                self.signals.status_message.emit("실패: 후크 생성 오류")

        except InterruptedError:
            self.signals.log_message.emit("<b><span style='color:orange;'>숏츠 후크 생성 작업이 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>숏츠 후크 생성 중 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    def generate_shorts_hashtags_action(self):
        """숏츠 해시태그 최적화 버튼 클릭 시 호출되는 함수"""
        transcript_content = self.last_loaded_transcript_content if hasattr(self, 'last_loaded_transcript_content') else ""
        
        if not transcript_content:
            QMessageBox.warning(self, "입력 오류", "먼저 영상 대본을 로드하거나 생성해야 합니다.")
            return

        platform = self.shorts_platform_combo.currentText()
        content_type = self.shorts_type_combo.currentText()

        if self.processor and self.processor.gemini_model:
            self.signals.log_message.emit(f"<b>\n숏츠 해시태그 최적화 시작 ({platform})...</b>")
            self.shorts_hashtags_output.clear()
            self.generate_shorts_hashtags_btn.setEnabled(False)
            self.status_label.setText("해시태그 최적화 중...")

            self.current_thread = threading.Thread(
                target=self._generate_shorts_hashtags_thread, 
                args=(transcript_content, platform, content_type,),
                daemon=True
            )
            self.current_thread.start()
        else:
            QMessageBox.warning(self, "경고", "Gemini API가 설정되지 않았거나 모델이 로드되지 않았습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.")
            self.signals.log_message.emit("<span style='color:red;'>Gemini API가 설정되지 않아 해시태그를 생성할 수 없습니다.</span>")

    def _generate_shorts_hashtags_thread(self, transcript_content, platform, content_type):
        """숏츠 해시태그 최적화 스레드"""
        try:
            self.signals.progress.emit(10)
            generated_hashtags = self.processor.generate_shorts_hashtags(transcript_content, platform, content_type)
            
            if generated_hashtags:
                print(f"[DEBUG_GUI] 생성된 숏츠 해시태그: {generated_hashtags[:100]}...")
                self.signals.shorts_hashtags_output.emit(generated_hashtags)
                self.signals.log_message.emit("<b>\n숏츠 해시태그 최적화 완료!</b>")
                self.signals.status_message.emit("해시태그 최적화 완료")
                self.signals.progress.emit(100)
            else:
                self.signals.log_message.emit("<span style='color:orange;'>숏츠 해시태그 최적화에 실패했습니다.</span>")
                self.signals.status_message.emit("실패: 해시태그 생성 오류")

        except InterruptedError:
            self.signals.log_message.emit("<b><span style='color:orange;'>숏츠 해시태그 최적화 작업이 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>숏츠 해시태그 최적화 중 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    def generate_shorts_timeline_action(self):
        """숏츠 편집 타임라인 생성 버튼 클릭 시 호출되는 함수"""
        transcript_content = self.last_loaded_transcript_content if hasattr(self, 'last_loaded_transcript_content') else ""
        
        if not transcript_content:
            QMessageBox.warning(self, "입력 오류", "먼저 영상 대본을 로드하거나 생성해야 합니다.")
            return

        video_length = self.shorts_length_combo.currentText()
        platform = self.shorts_platform_combo.currentText()

        if self.processor and self.processor.gemini_model:
            self.signals.log_message.emit(f"<b>\n숏츠 편집 타임라인 생성 시작 ({video_length}, {platform})...</b>")
            self.shorts_timeline_output.clear()
            self.generate_shorts_timeline_btn.setEnabled(False)
            self.status_label.setText("편집 타임라인 생성 중...")

            self.current_thread = threading.Thread(
                target=self._generate_shorts_timeline_thread, 
                args=(transcript_content, video_length, platform,),
                daemon=True
            )
            self.current_thread.start()
        else:
            QMessageBox.warning(self, "경고", "Gemini API가 설정되지 않았거나 모델이 로드되지 않았습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.")
            self.signals.log_message.emit("<span style='color:red;'>Gemini API가 설정되지 않아 타임라인을 생성할 수 없습니다.</span>")

    def _generate_shorts_timeline_thread(self, transcript_content, video_length, platform):
        """숏츠 편집 타임라인 생성 스레드"""
        try:
            self.signals.progress.emit(10)
            generated_timeline = self.processor.generate_shorts_timeline(transcript_content, video_length, platform)
            
            if generated_timeline:
                print(f"[DEBUG_GUI] 생성된 숏츠 타임라인: {generated_timeline[:100]}...")
                self.signals.shorts_timeline_output.emit(generated_timeline)
                self.signals.log_message.emit("<b>\n숏츠 편집 타임라인 생성 완료!</b>")
                self.signals.status_message.emit("편집 타임라인 생성 완료")
                self.signals.progress.emit(100)
            else:
                self.signals.log_message.emit("<span style='color:orange;'>숏츠 편집 타임라인 생성에 실패했습니다.</span>")
                self.signals.status_message.emit("실패: 타임라인 생성 오류")

        except InterruptedError:
            self.signals.log_message.emit("<b><span style='color:orange;'>숏츠 편집 타임라인 생성 작업이 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>숏츠 편집 타임라인 생성 중 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    def generate_shorts_ab_test_action(self):
        """숏츠 A/B 테스트 시나리오 생성 버튼 클릭 시 호출되는 함수"""
        transcript_content = self.last_loaded_transcript_content if hasattr(self, 'last_loaded_transcript_content') else ""
        
        if not transcript_content:
            QMessageBox.warning(self, "입력 오류", "먼저 영상 대본을 로드하거나 생성해야 합니다.")
            return

        platform = self.shorts_platform_combo.currentText()
        content_type = self.shorts_type_combo.currentText()

        if self.processor and self.processor.gemini_model:
            self.signals.log_message.emit(f"<b>\n숏츠 A/B 테스트 시나리오 생성 시작 ({platform})...</b>")
            self.shorts_ab_test_output.clear()
            self.generate_shorts_ab_test_btn.setEnabled(False)
            self.status_label.setText("A/B 테스트 시나리오 생성 중...")

            self.current_thread = threading.Thread(
                target=self._generate_shorts_ab_test_thread, 
                args=(transcript_content, platform, content_type,),
                daemon=True
            )
            self.current_thread.start()
        else:
            QMessageBox.warning(self, "경고", "Gemini API가 설정되지 않았거나 모델이 로드되지 않았습니다. GOOGLE_API_KEY 환경 변수를 확인해주세요.")
            self.signals.log_message.emit("<span style='color:red;'>Gemini API가 설정되지 않아 A/B 테스트 시나리오를 생성할 수 없습니다.</span>")

    def _generate_shorts_ab_test_thread(self, transcript_content, platform, content_type):
        """숏츠 A/B 테스트 시나리오 생성 스레드"""
        try:
            self.signals.progress.emit(10)
            generated_ab_test = self.processor.generate_shorts_ab_test(transcript_content, platform, content_type)
            
            if generated_ab_test:
                print(f"[DEBUG_GUI] 생성된 숏츠 A/B 테스트: {generated_ab_test[:100]}...")
                self.signals.shorts_ab_test_output.emit(generated_ab_test)
                self.signals.log_message.emit("<b>\n숏츠 A/B 테스트 시나리오 생성 완료!</b>")
                self.signals.status_message.emit("A/B 테스트 시나리오 생성 완료")
                self.signals.progress.emit(100)
            else:
                self.signals.log_message.emit("<span style='color:orange;'>숏츠 A/B 테스트 시나리오 생성에 실패했습니다.</span>")
                self.signals.status_message.emit("실패: A/B 테스트 시나리오 생성 오류")

        except InterruptedError:
            self.signals.log_message.emit("<b><span style='color:orange;'>숏츠 A/B 테스트 시나리오 생성 작업이 중지되었습니다.</span></b>")
            self.signals.status_message.emit("중지됨")
        except Exception as e:
            self.signals.log_message.emit(f"<span style='color:red;'>숏츠 A/B 테스트 시나리오 생성 중 오류 발생: {e}</span>")
            self.signals.status_message.emit("오류 발생")
        finally:
            self.signals.finished.emit()

    def export_shorts_results_action(self):
        """숏츠 제작 결과 내보내기 버튼 클릭 시 호출되는 함수"""
        # 숏츠 제작 결과들 가져오기
        shorts_script = self.shorts_script_output.toPlainText()
        shorts_hook = self.shorts_hook_output.toPlainText()
        shorts_hashtags = self.shorts_hashtags_output.toPlainText()
        shorts_timeline = self.shorts_timeline_output.toPlainText()
        shorts_ab_test = self.shorts_ab_test_output.toPlainText()

        # 설정 정보 가져오기
        video_length = self.shorts_length_combo.currentText()
        platform = self.shorts_platform_combo.currentText()
        content_type = self.shorts_type_combo.currentText()

        # 원본 대본 가져오기
        original_transcript = self.last_loaded_transcript_content if hasattr(self, 'last_loaded_transcript_content') else ""
        video_title = self.last_loaded_video_title if hasattr(self, 'last_loaded_video_title') else "Unknown_Video"

        if not (shorts_script or shorts_hook or shorts_hashtags or shorts_timeline or shorts_ab_test):
            QMessageBox.warning(self, "내보내기 오류", "내보낼 숏츠 제작 결과가 없습니다. 먼저 숏츠 제작 기능을 사용해주세요.")
            return

        # 통합 콘텐츠 생성
        combined_content = f"""# 숏츠 제작 지원 결과

## 📋 기본 정보
- **원본 영상 제목**: {video_title}
- **숏츠 길이**: {video_length}
- **타겟 플랫폼**: {platform}
- **콘텐츠 유형**: {content_type}

## 📝 원본 대본
{original_transcript}

"""

        if shorts_script:
            combined_content += f"""
## 🎬 숏츠 스크립트
{shorts_script}

"""

        if shorts_hook:
            combined_content += f"""
## 🎣 후크(Hook) 제안
{shorts_hook}

"""

        if shorts_hashtags:
            combined_content += f"""
## 🏷️ 최적화된 해시태그
{shorts_hashtags}

"""

        if shorts_timeline:
            combined_content += f"""
## ⏱️ 편집 타임라인
{shorts_timeline}

"""

        if shorts_ab_test:
            combined_content += f"""
## 🧪 A/B 테스트 시나리오
{shorts_ab_test}

"""

        # 파일 저장
        gpt_data_folder = Path("GPT_data")
        gpt_data_folder.mkdir(parents=True, exist_ok=True)

        # 파일명 생성
        safe_title = re.sub(r'[\\/:*?"<>|]', '', video_title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_file_name = f"shorts_creation_{safe_title}_{timestamp}.txt"

        file_name, _ = QFileDialog.getSaveFileName(
            self, 
            "숏츠 제작 결과 저장", 
            str(gpt_data_folder / default_file_name), 
            "텍스트 파일 (*.txt);;모든 파일 (*)"
        )

        if file_name:
            try:
                with open(file_name, 'w', encoding='utf-8') as f:
                    f.write(combined_content)
                
                QMessageBox.information(
                    self, 
                    "저장 성공", 
                    f"숏츠 제작 결과가 다음 위치에 저장되었습니다:\n{file_name}"
                )

                # 추가로 ChatGPT 프롬프트 생성
                chatgpt_prompt = f"""
다음은 숏츠 제작을 위한 분석 결과입니다. 이 자료를 바탕으로 실제 숏츠 제작에 활용할 수 있는 구체적인 가이드를 제공해주세요.

--- 숏츠 제작 분석 결과 ---
{combined_content}
---

다음 항목들을 포함하여 숏츠 제작 가이드를 작성해주세요:

1. **편집 소프트웨어 추천** (CapCut, Premiere Pro, Final Cut Pro 등)
2. **시각적 효과 제안** (자막 스타일, 전환 효과, 필터 등)
3. **음악/효과음 추천** (플랫폼별 인기 음악 스타일)
4. **썸네일 제작 가이드** (시선을 사로잡는 썸네일 디자인)
5. **업로드 최적 시간** (플랫폼별 최적 업로드 시간)
6. **성과 측정 방법** (조회수, 좋아요, 댓글, 공유 분석)
7. **후속 콘텐츠 아이디어** (시리즈물 기획)

실용적이고 구체적인 조언을 제공해주세요.
"""

                QMessageBox.information(
                    self, 
                    "ChatGPT 프롬프트", 
                    chatgpt_prompt
                )

            except Exception as e:
                QMessageBox.critical(
                    self, 
                    "저장 오류", 
                    f"파일 저장 중 오류가 발생했습니다:\n{e}"
                )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TikTokGUI()
    window.show()
    sys.exit(app.exec_()) 