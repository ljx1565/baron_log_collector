"""
로그 로테이션(logrotate)에 안전한 파일 tail 유틸리티.

일반적인 tail -f 방식은 파일이 로테이션되어 새 inode로 바뀌면
계속 옛 파일(삭제된 inode)을 붙잡고 있어서 새 로그를 놓치게 된다.
여기서는 주기적으로 경로의 inode를 확인해서, 바뀌었으면 새로 열도록 한다.
"""

import logging
import os
import time

logger = logging.getLogger("tailer")


class RotationSafeTailer:
    def __init__(self, path, poll_interval=1.0, from_end=True, wait_for_file_sec=5.0):
        self.path = path
        self.poll_interval = poll_interval
        self.wait_for_file_sec = wait_for_file_sec
        self._fh = None
        self._inode = None
        self._open(from_end=from_end)

    def _open(self, from_end=False):
        if self._fh:
            try:
                self._fh.close()
            except Exception:
                pass

        warned = False
        while True:
            try:
                self._fh = open(self.path, "r", encoding="utf-8", errors="replace")
                break
            except FileNotFoundError:
                if not warned:
                    logger.warning(
                        "로그 파일이 아직 없습니다. 해당 서비스가 설치/실행 중인지 확인하세요. "
                        "생길 때까지 대기: %s", self.path
                    )
                    warned = True
                time.sleep(self.wait_for_file_sec)

        self._inode = os.fstat(self._fh.fileno()).st_ino
        if from_end:
            self._fh.seek(0, os.SEEK_END)

    def _rotated(self):
        try:
            current_inode = os.stat(self.path).st_ino
        except FileNotFoundError:
            # 로테이션 도중 잠깐 파일이 없을 수 있음 -> 다음 폴링에 재시도
            return False
        return current_inode != self._inode

    def follow(self):
        """새 로그 라인이 생길 때마다 yield 하는 제너레이터. 무한 루프이므로
        스레드/프로세스에서 실행할 것."""
        while True:
            line = self._fh.readline()
            if line:
                yield line.rstrip("\n")
                continue

            # 더 읽을 라인이 없음: 로테이션 여부 확인 후 대기
            if self._rotated():
                self._open(from_end=False)
                continue

            time.sleep(self.poll_interval)
