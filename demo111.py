import sys
import os
import live2d.v3 as live2d
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QKeyEvent, QCursor
from PyQt5.QtWidgets import QApplication, QMainWindow, QOpenGLWidget, QMenu, QAction, QMessageBox
from OpenGL.GL import glClear, glClearColor, GL_POINTS, GL_COLOR_BUFFER_BIT
from OpenGL.GL import GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, glDepthFunc, glEnable, glViewport
import random
import keyboard


# 获取运行时的资源路径
BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

MODEL_PATH = os.path.join(BASE_DIR, 'model')

print(f"Resource Path: {MODEL_PATH}")



class Live2DWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None  # Live2D 模型对象
        self.resize(400, 400)  # 设置窗口大小

        # 定时器来周期性地更新模型角度
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateModelAngle)
        self.timer.start(16)  # 每16毫秒更新一次，大约60FPS

        # 记录上次光标的位置
        self.last_cursor_pos = None
        self.target_angle_x = 0.0
        self.target_angle_y = 0.0
        self.current_angle_x = 0.0
        self.current_angle_y = 0.0
        self.angle_smooth_speed = 0.1  # 平滑过渡速度

        self.current_expression = 'expression0'  # 当前表情



    def initializeGL(self):
        """
        初始化 OpenGL 和 Live2D 环境
        """
        try:
            live2d.glewInit()
            live2d.setGLProperties()
            live2d.init()

            # 加载模型
            self.model = live2d.LAppModel()
            model_path = os.path.join(MODEL_PATH, 'demomodel.model3.json')
            self.model.LoadModelJson(model_path)
            self.model.Resize(self.width(), self.height())  # 设置模型的初始大小

        except Exception as e:
            QMessageBox.critical(self, "加载模型失败", f"模型文件加载失败: {e}")
            return

    def resizeGL(self, width, height):
        """
        窗口大小变化时，更新 OpenGL 视口
        """
        glViewport(0, 0, width, height)
        if self.model:
            self.model.Resize(width, height)  # 确保模型已加载再调整大小

    def paintGL(self):
        """
        每帧绘制模型
        """
        glClearColor(0, 0, 0, 0)  # 设置清除颜色为透明
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self.model:  # 确保模型已加载后才执行更新和绘制

            self.model.SetExpression(self.current_expression)
            self.model.Update()  # 更新模型（基于参数）
            # 确保在每帧渲染之前重设模型的角度
            self.model.SetParameterValue("ParamAngleX", self.current_angle_x, 1.0)
            self.model.SetParameterValue("ParamAngleY", self.current_angle_y, 1.0)

            self.model.Draw()  # 绘制模型
            self.update()


    def updateModelAngle(self):
        """
        根据光标位置更新模型角度，加入平滑过渡和缓冲效果
        """
        if self.model:
            # 获取当前鼠标位置
            cursor_pos = QCursor.pos()

            # 计算光标在窗口内的相对位置
            window_pos = self.mapFromGlobal(cursor_pos)

            # 如果光标位置没有变化，不更新角度
            # if self.last_cursor_pos == window_pos:
            #     return

            # 更新光标位置
            self.last_cursor_pos = window_pos

            # 获取窗口的大小
            window_width = self.width()
            window_height = self.height()

            # 将光标位置映射到 [-30.0, 30.0] 范围内
            target_angle_x = round(- (window_pos.x() / window_width) * 60.0 + 30.0, 1)  # 映射到 [-30.0, 30.0] 范围
            target_angle_y = round(- (window_pos.y() / window_height) * 60.0 + 30.0, 1)  # 映射到 [-30.0, 30.0] 范围

            # 设置缓冲系数，这个值控制平滑过渡的速度
            smoothing_factor = 0.1  # 增大此值可使动画响应更平滑

            # 平滑过渡角度
            self.target_angle_x = target_angle_x
            self.target_angle_y = target_angle_y

            # 使用插值方法（线性插值）平滑过渡角度
            self.current_angle_x += (self.target_angle_x - self.current_angle_x) * smoothing_factor
            self.current_angle_y += (self.target_angle_y - self.current_angle_y) * smoothing_factor

            # 确保模型的角度不会超过指定的范围
            self.current_angle_x = max(min(self.current_angle_x, 30.0), -30.0)
            self.current_angle_y = max(min(self.current_angle_y, 30.0), -30.0)


class Live2DWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpacervalLam")  # 设置窗口标题
        self.setGeometry(100, 100, 500, 400)  # 设置窗口位置和大小

        # 设置窗口为透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)  # 设置窗口透明
        self.setWindowFlags(
            self.windowFlags() | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)  # 去掉窗口边框并始终置顶，且不显示在任务栏
        self.setWindowOpacity(1.0)  # 确保窗口不透明

        # 创建并设置 OpenGL Widget
        self.live2d_widget = Live2DWidget(self)
        self.setCentralWidget(self.live2d_widget)

        # 显示窗口
        self.show()

        # 注册全局快捷键 Ctrl + Space
        try:
            keyboard.add_hotkey('ctrl+space', self.toggle_hide)
        except Exception as e:
            print(f"快捷键注册失败: {e}")

        # 用于存储鼠标点击的起始位置
        self.drag_position = QPoint()
        self.is_resizing = False  # 用于控制是否处于调整大小模式
        self.is_locked = False  # 用于控制窗口是否锁定

        # 限制最大尺寸
        self.max_width = 1100
        self.max_height = 1100

        # 表情状态变量，初始为expression0
        self.current_expression = 'expression0'

    def closeEvent(self, event):
        """
        关闭事件，清理资源
        """
        live2d.dispose()  # 释放 Live2D 模型资源
        keyboard.unhook_all()  # 清除所有热键的注册
        event.accept()

    def mousePressEvent(self, event):
        """
        捕捉鼠标按下事件，记录当前鼠标的位置
        """
        if event.button() == Qt.LeftButton:
            if not self.is_locked:
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                self.is_resizing = False  # 按下时不调整大小
            else:
                # 如果窗口被锁定，进行随机移动
                screen_rect = QApplication.desktop().screenGeometry()  # 获取屏幕的可用区域
                screen_width, screen_height = screen_rect.width(), screen_rect.height()

                # 当前窗口的位置
                current_x, current_y = self.x(), self.y()

                # 计算随机偏移量，偏移量为窗口大小的1倍
                random_offset_x = random.randint(-int(self.width()), int(self.width()))
                random_offset_y = random.randint(-int(self.height()), int(self.height()))

                # 计算新的位置，并确保不超出屏幕范围
                new_x = max(0, min(screen_width - self.width(), current_x + random_offset_x))
                new_y = max(0, min(screen_height - self.height(), current_y + random_offset_y))

                # 移动窗口
                self.move(new_x, new_y)

    def mouseMoveEvent(self, event):
        """
        捕捉鼠标移动事件，更新窗口的位置
        """
        if event.buttons() == Qt.LeftButton and not self.is_resizing and not self.is_locked:
            self.move(event.globalPos() - self.drag_position)

    def wheelEvent(self, event):
        """
        捕捉滚轮事件，用于调整窗口大小
        """
        if not self.is_locked:
            if event.angleDelta().y() > 0:  # 上滚
                self.resize(self.width() + 10, self.height() + 10)
            elif event.angleDelta().y() < 0:  # 下滚
                self.resize(self.width() - 10, self.height() - 10)

            # 限制窗口大小在最大尺寸范围内
            if self.width() > self.max_width:
                self.resize(self.max_width, self.height())
            if self.height() > self.max_height:
                self.resize(self.width(), self.max_height)

            # 防止窗口缩小到小于最小尺寸
            if self.width() < 200 or self.height() < 200:
                self.resize(200, 200)

    def close_program(self):
        """
        关闭程序
        """
        self.close()
        QApplication.quit()
        sys.exit()

    def contextMenuEvent(self, event):
        """
        捕捉右键点击事件，显示右键菜单
        """
        menu = QMenu(self)

        # 创建"关闭程序"菜单项
        close_action = QAction("byebye", self)
        close_action.triggered.connect(self.close_program)  # 绑定关闭窗口的槽
        menu.addAction(close_action)

        # 创建"使用说明"菜单项
        help_action = QAction("领养说明", self)
        help_action.triggered.connect(self.show_help)  # 绑定显示帮助的槽
        menu.addAction(help_action)

        # 创建"锁定/解锁窗口"菜单项
        lock_action = QAction("不准动！", self)
        lock_action.setCheckable(True)
        lock_action.setChecked(self.is_locked)
        lock_action.triggered.connect(self.toggle_lock)

        if self.is_locked:
            lock_action.setText("可以动了")
        menu.addAction(lock_action)

        # 创建"藏起来"菜单项
        hide_action = QAction("藏起来", self)
        hide_action.triggered.connect(self.toggle_hide)  # 绑定隐藏/显示窗口的槽
        menu.addAction(hide_action)

        # 创建"切换表情"菜单项
        toggle_expression_action = QAction("hate", self)
        toggle_expression_action.triggered.connect(self.toggle_expression)  # 绑定切换表情的槽
        menu.addAction(toggle_expression_action)

        # 显示菜单
        menu.exec_(event.globalPos())

    def toggle_hide(self):
        """
        切换窗口的显示和隐藏
        确保在主线程中执行窗口的展示或隐藏
        """
        if self.isHidden():
            QTimer.singleShot(0, self.show)  # 使用 QTimer 确保在主线程中执行
        else:
            QTimer.singleShot(0, self.hide)  # 使用 QTimer 隐藏窗口

    def show_help(self):
        """
        显示程序使用说明
        """
        QMessageBox.information(self, "SpacervalLam の 说明",
                                "1.将光标放在桌宠上并滚动鼠标滚轮可以缩放大小\n\n2.按住桌宠并拖动可以改变位置\n\n快捷键：Ctrl + Space 隐藏/显示\n\n”")

    def toggle_lock(self):
        """
        锁定或解锁窗口
        """
        self.is_locked = not self.is_locked
        if self.is_locked:
            self.setWindowTitle("SpacervalLam (locked)")
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # 锁定时允许鼠标穿透窗口
        else:
            self.setWindowTitle("SpacervalLam")
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)  # 解锁时恢复正常鼠标事件捕获

    def toggle_expression(self):
        """
        切换表情
        """
        if self.current_expression == 'expression0':
            self.current_expression = 'expression1'
        else:
            self.current_expression = 'expression0'

        # 设置新的表情
        self.live2d_widget.current_expression = self.current_expression


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Live2DWindow()
    print("程序启动成功！")
    sys.exit(app.exec_())
