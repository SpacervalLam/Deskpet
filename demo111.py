import sys
import os
import live2d.v3 as live2d
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QKeyEvent, QCursor, QPainter, QRadialGradient, QColor, QIcon
from PyQt5.QtWidgets import QApplication, QMainWindow, QOpenGLWidget, QMenu, QAction, QMessageBox, QSystemTrayIcon
from OpenGL.GL import glClear, glClearColor, GL_POINTS, GL_COLOR_BUFFER_BIT
from OpenGL.GL import GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, glDepthFunc, glEnable, glViewport
import random
import keyboard
import win32gui
import win32con


# 资源路径
BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, 'model')


# 自定义 FancyMenu，实现从中心向外的径向渐变（支持 hover 渐进动画）
class FancyMenu(QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 关键设置：完全禁用 QMenu 和 QMenu::item 的原生背景绘制
        self.setStyleSheet("""
            QMenu {
                background-color: rgba(0, 0, 0, 0); /* 完全透明背景 */
                border: none; /* 无边框 */
                padding: 0px; /* 无内边距 */
            }
            QMenu::item {
                background-color: rgba(0, 0, 0, 0); /* 菜单项完全透明背景 */
                padding: 12px 30px;
                color: #ffffff;
                font-size: 22px;
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                border-left: 3px solid transparent;
            }
            QMenu::item:hover {
                color: #4299e1;
                border-left-color: #4299e1;
            }
            QMenu::item:selected {
                color: #63b3ed;
                border-left-color: #63b3ed;
            }
        """)
        self.setMouseTracking(True)
        self.hovered_action = None
        self._anim_progress = 1.0  # 动画进度
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(16)
        self.anim_timer.timeout.connect(self._anim_step)
        self.anim_timer.start()

        # 连接 hovered 信号，用于记录当前悬停的 action
        self.hovered.connect(self._on_hovered)

    def _on_hovered(self, action):
        # 记录当前悬停的 action 并重置动画进度
        self.hovered_action = action
        self._anim_progress = 0.0
        self.update()

    def _anim_step(self):
        # 简单推进动画进度
        if self._anim_progress < 1.0:
            self._anim_progress = min(1.0, self._anim_progress + 0.08)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 为每个 action 绘制径向渐变背景（中心到外渐变透明）
        for action in self.actions():
            rect = self.actionGeometry(action)
            if rect.isValid() and not rect.isEmpty():
                # 基础颜色（非 hover）
                base_center_color = QColor(20, 25, 40, 220)
                base_mid_color = QColor(20, 25, 40, 80)
                base_edge_color = QColor(20, 25, 40, 0)

                if action == self.hovered_action:
                    # hover 时颜色更亮，且使用 anim_progress 控制强度或半径
                    t = self._anim_progress
                    center_alpha = int(210 * t + 120 * (1 - t))
                    mid_alpha = int(140 * t + 50 * (1 - t))
                    base_center_color = QColor(66, 153, 225, center_alpha)
                    base_mid_color = QColor(66, 153, 225, mid_alpha)
                    base_edge_color = QColor(66, 153, 225, 0)

                # radial gradient 中心设在 item 的中心
                cx = rect.x() + rect.width() / 2.0
                cy = rect.y() + rect.height() / 2.0
                radius = max(rect.width(), rect.height()) * (0.9 + 0.25 * self._anim_progress)

                grad = QRadialGradient(cx, cy, radius, cx, cy)
                grad.setColorAt(0.0, base_center_color)
                grad.setColorAt(0.5, base_mid_color)
                grad.setColorAt(1.0, base_edge_color)

                # 绘制渐变背景，使用圆角矩形
                painter.setBrush(grad)
                painter.setPen(Qt.NoPen)  # 无边框
                painter.drawRoundedRect(rect.adjusted(4, 2, -4, -2), 8, 8)

        painter.end()

        # 让 QMenu 的默认绘制继续绘制文本/图标/选中框等
        super().paintEvent(event)



class Live2DWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None  # Live2D 模型对象
        self.resize(800, 800)  # 设置窗口大小，扩大一倍

        # 定时器来周期性地更新模型角度
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateModelAngle)
        self.timer.start(16)  # 每16毫秒更新一次，大约60FPS

        # 状态变量初始化
        self.last_cursor_pos = None
        self.target_angle_x = 0.0
        self.target_angle_y = 0.0
        self.current_angle_x = 0.0
        self.current_angle_y = 0.0
        self.angle_smooth_speed = 0.1

        self.current_expression = None  # 不使用表情避免日志输出
        
        # 嘴巴呼吸效果
        self.target_mouth_open = 0.1
        self.current_mouth_open = 0.1
        self.mouth_smooth_speed = 0.008
        self.breath_timer = 0
        self.breath_interval = 120
        self.min_open_value = 0.08
        self.max_open_value = 0.2
        
        # 手臂参数
        self.target_arm_left = -10.0
        self.current_arm_left = -10.0
        self.target_arm_right = -10.0
        self.current_arm_right = -10.0
        
        # 眨眼效果
        self.eye_open = 1.0
        self.target_eye_open = 1.0
        self.eye_smooth_speed = 0.15
        self.blink_timer = 0
        self.blink_interval = random.randint(300, 600)
        
        # 手臂固定相关变量
        self.current_arm_left = -10.0  # 当前左手臂旋转角度（初始为-10）
        self.current_arm_right = -10.0  # 当前右手臂旋转角度（初始为-10）
        
        # CTRL+鼠标按下状态标志
        self.is_ctrl_mouse_pressed = False



    def initializeGL(self):
        """
        初始化 OpenGL 和 Live2D 环境
        """
        try:
            live2d.glInit()
            live2d.init()

            # 加载模型
            self.model = live2d.LAppModel()
            model_path = os.path.join(MODEL_PATH, 'sef.model3.json')
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

            if self.current_expression is not None:
                self.model.SetExpression(self.current_expression)
            self.model.Update()  # 更新模型（基于参数）
            # 确保在每帧渲染之前重设模型的角度
            self.model.SetParameterValue("ParamAngleX", self.current_angle_x, 1.0)
            self.model.SetParameterValue("ParamAngleY", self.current_angle_y, 1.0)
            
            # 设置瞳孔左右移动参数
            if hasattr(self, 'current_eyeball_x'):
                self.model.SetParameterValue("ParamEyeBallX", self.current_eyeball_x, 1.0)
                # 大多数Live2D模型也有垂直瞳孔移动参数，这里一并设置
                # 垂直移动通常较水平移动幅度小
                if hasattr(self, 'current_angle_y'):
                    # 将头部Y角度转换为瞳孔Y移动，使用较小的系数
                    eyeball_y = self.current_angle_y * 0.03
                    self.model.SetParameterValue("ParamEyeBallY", eyeball_y, 1.0)
            
            # 添加身体旋转参数绑定，优化参数比例使效果更自然
            body_angle_x = self.current_angle_x * 0.25  # 身体X轴旋转（较小幅度）
            body_angle_y = self.current_angle_y * 0.2   # 身体Y轴旋转（更小幅度）
            # 改进Z轴旋转计算，结合X和Y角度，创造更自然的扭转效果
            body_angle_z = (self.current_angle_x * 0.15) + (self.current_angle_y * 0.05)
            
            self.model.SetParameterValue("ParamBodyAngleX", body_angle_x, 1.0)
            self.model.SetParameterValue("ParamBodyAngleY", body_angle_y, 1.0)
            self.model.SetParameterValue("ParamBodyAngleZ", body_angle_z, 1.0)
            
            # 设置嘴巴开闭参数
            self.model.SetParameterValue("ParamMouthOpenY", self.current_mouth_open, 1.0)
            
            # 设置眼睛开闭参数 - 左右眼使用相同的值
            self.model.SetParameterValue("ParamEyeLOpen", self.eye_open, 1.0)
            self.model.SetParameterValue("ParamEyeROpen", self.eye_open, 1.0)
            
            # 设置手臂旋转参数
            self.model.SetParameterValue("ParamShoulderLRotation", self.current_arm_left, 1.0)
            self.model.SetParameterValue("ParamShoulderRRotation", self.current_arm_right, 1.0)

            self.model.Draw()  # 绘制模型
            self.update()


    def updateModelAngle(self):
        """
        根据光标位置更新模型角度、瞳孔移动和手臂旋转，加入平滑过渡和缓冲效果
        同时实现嘴巴开闭的随机呼吸效果
        """
        if self.model:
            # 获取当前鼠标位置
            cursor_pos = QCursor.pos()

            # 计算光标在窗口内的相对位置
            window_pos = self.mapFromGlobal(cursor_pos)

            # 更新光标位置
            self.last_cursor_pos = window_pos

            # 获取窗口的大小
            window_width = self.width()
            window_height = self.height()

            # 将光标位置映射到 [-30.0, 30.0] 范围内
            # 修复左右方向反转问题，移除target_angle_x前的负号
            target_angle_x = round((window_pos.x() / window_width) * 60.0 - 30.0, 1)  # 映射到 [-30.0, 30.0] 范围
            target_angle_y = round(- (window_pos.y() / window_height) * 60.0 + 30.0, 1)  # 映射到 [-30.0, 30.0] 范围
            
            # 计算瞳孔左右移动参数 - 将光标位置映射到瞳孔移动范围 [-1.0, 1.0]
            # 瞳孔移动通常比头部转动更敏感，这里使用0.8的系数稍微降低敏感度
            target_eyeball_x = round(((window_pos.x() / window_width) * 2.0 - 1.0) * 0.8, 2)
            
            # 根据鼠标位置计算手臂旋转角度
            # 当鼠标向左移动时，左臂向内旋转(负角度)，右臂向外旋转(正角度)
            # 当鼠标向右移动时，左臂向外旋转(正角度)，右臂向内旋转(负角度)
            # 手臂旋转幅度为头部的1/4，使动作更自然
            arm_rotation_factor = 0.25
            target_arm_left = -target_angle_x * arm_rotation_factor  # 左臂旋转方向与头部相反
            target_arm_right = target_angle_x * arm_rotation_factor  # 右臂旋转方向与头部相同

            # 设置缓冲系数，这个值控制平滑过渡的速度
            smoothing_factor = 0.1  # 增大此值可使动画响应更平滑

            # 平滑过渡角度
            self.target_angle_x = target_angle_x
            self.target_angle_y = target_angle_y
            
            # 平滑过渡瞳孔位置（使用略大的平滑系数使瞳孔移动更自然）
            if not hasattr(self, 'target_eyeball_x'):
                self.target_eyeball_x = 0.0
                self.current_eyeball_x = 0.0
            self.target_eyeball_x = target_eyeball_x
            
            # 初始化手臂目标角度
            if not hasattr(self, 'target_arm_left'):
                self.target_arm_left = -10.0
            if not hasattr(self, 'target_arm_right'):
                self.target_arm_right = -10.0
            
            # 检查是否按住CTRL+鼠标，如果是则设置特殊效果
            if self.is_ctrl_mouse_pressed:
                # 设置眼睛关闭
                self.target_eye_open = 0.0
                # 设置手臂参数为最小值
                self.target_arm_left = -15.0
                self.target_arm_right = -15.0
                # 设置嘴巴闭合并取最小值
                self.target_mouth_open = self.min_open_value
            else:
                # 正常模式下更新手臂角度
                if abs(target_arm_left) > 0.1 or abs(target_arm_right) > 0.1:
                    self.target_arm_left = target_arm_left
                    self.target_arm_right = target_arm_right

            # 使用插值方法（线性插值）平滑过渡角度、瞳孔位置和手臂旋转
            self.current_angle_x += (self.target_angle_x - self.current_angle_x) * smoothing_factor
            self.current_angle_y += (self.target_angle_y - self.current_angle_y) * smoothing_factor
            self.current_eyeball_x += (self.target_eyeball_x - self.current_eyeball_x) * (smoothing_factor * 1.2)
            # 手臂旋转使用略小的平滑系数，使动作更迟缓一些
            self.current_arm_left += (self.target_arm_left - self.current_arm_left) * (smoothing_factor * 0.8)
            self.current_arm_right += (self.target_arm_right - self.current_arm_right) * (smoothing_factor * 0.8)

            # 确保模型的角度不会超过指定的范围
            self.current_angle_x = max(min(self.current_angle_x, 30.0), -30.0)
            self.current_angle_y = max(min(self.current_angle_y, 30.0), -30.0)
            # 确保瞳孔移动在合理范围内
            self.current_eyeball_x = max(min(self.current_eyeball_x, 1.0), -1.0)
            # 确保手臂旋转在合理范围内（正方向不超过0度，负方向可以到-15.0度）
            self.current_arm_left = max(min(self.current_arm_left, 0), -15.0)
            self.current_arm_right = max(min(self.current_arm_right, 0), -15.0)
            
            # 嘴巴呼吸效果已经在非CTRL+鼠标按下状态中处理
            
            # 平滑过渡
            self.current_mouth_open += (self.target_mouth_open - self.current_mouth_open) * self.mouth_smooth_speed
            self.current_mouth_open = max(min(self.current_mouth_open, self.max_open_value), self.min_open_value)
            
            # 只有在非CTRL+鼠标按下状态时才执行正常眨眼和呼吸逻辑
            if not self.is_ctrl_mouse_pressed:
                # 眨眼效果
                self.blink_timer += 1
                if self.blink_timer >= self.blink_interval:
                    self.blink_timer = 0
                    self.target_eye_open = 0.0
                    self.blink_interval = random.randint(120, 480)
                
                # 眨眼过程控制
                if self.target_eye_open == 0.0 and self.eye_open < 0.1:
                    if self.blink_timer < random.randint(10, 20):
                        self.target_eye_open = 0.0
                    else:
                        self.target_eye_open = 1.0
                
                # 嘴巴呼吸效果
                self.breath_timer += 1
                if self.breath_timer >= self.breath_interval:
                    self.breath_timer = 0
                    change_amount = random.uniform(-0.15, 0.15)
                    self.target_mouth_open += change_amount
                    self.target_mouth_open = max(min(self.target_mouth_open, self.max_open_value), self.min_open_value)
                    self.breath_interval = random.randint(90, 180)
            
            # 平滑过渡眼睛
            self.eye_open += (self.target_eye_open - self.eye_open) * self.eye_smooth_speed
            self.eye_open = max(min(self.eye_open, 1.0), 0.0)
            


def set_window_transparent_for_mouse_events(hwnd, transparent):
    """
    使用Win32 API设置窗口的鼠标穿透属性
    hwnd: 窗口句柄
    transparent: 是否启用鼠标穿透
    """
    try:
        # 获取当前窗口样式
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        
        # 使用SetWindowLongPtr替代SetWindowLong，以支持64位系统
        if hasattr(win32gui, 'SetWindowLongPtr'):
            set_window_long = win32gui.SetWindowLongPtr
        else:
            set_window_long = win32gui.SetWindowLong
        
        if transparent:
            # 添加WS_EX_TRANSPARENT样式使鼠标事件穿透到下层窗口
            if not (style & win32con.WS_EX_TRANSPARENT):
                style |= win32con.WS_EX_TRANSPARENT
                set_window_long(hwnd, win32con.GWL_EXSTYLE, style)
        
        else:
            # 移除WS_EX_TRANSPARENT样式
            if style & win32con.WS_EX_TRANSPARENT:
                style &= ~win32con.WS_EX_TRANSPARENT
                set_window_long(hwnd, win32con.GWL_EXSTYLE, style)
        
        
        # 强制重绘窗口以确保样式变更生效
        win32gui.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                             win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | 
                             win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED)
    except Exception as e:
        pass

class Live2DWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpacervalLam")  # 设置窗口标题
        
        # 窗口大小设置
        window_width = 1000
        window_height = 800
        
        # 获取屏幕大小并计算右下角位置
        screen_rect = QApplication.desktop().availableGeometry()
        screen_width = screen_rect.width()
        screen_height = screen_rect.height()
        
        # 计算右下角位置（减去窗口宽度和高度，并向下移动一些）
        pos_x = screen_width - window_width
        pos_y = screen_height - window_height + 45
        
        # 设置窗口位置和大小（右下角）
        self.setGeometry(pos_x, pos_y, window_width, window_height)

        # 设置窗口为透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)  # 设置窗口透明
        self.setWindowFlags(
            self.windowFlags() | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)  # 去掉窗口边框并始终置顶，且不显示在任务栏
        self.setWindowOpacity(1.0)  # 确保窗口不透明
        
        # 默认允许鼠标穿透窗口，只有按住CTRL键时才响应鼠标事件
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        
        # 鼠标穿透状态标志
        self.is_mouse_transparent = True
        
        # 创建定时器来检测CTRL键状态
        self.ctrl_timer = QTimer(self)
        self.ctrl_timer.timeout.connect(self.check_ctrl_state)
        self.ctrl_timer.start(50)  # 每50毫秒检查一次

        # 创建并设置 OpenGL Widget
        self.live2d_widget = Live2DWidget(self)
        self.setCentralWidget(self.live2d_widget)

        # 显示窗口
        self.show()
        
        # 窗口显示后，应用初始的鼠标穿透设置
        self.apply_mouse_transparency(self.is_mouse_transparent)

        # 注册CTRL+space热键触发再见功能
        try:
            # 使用lambda和Qt的信号槽机制确保在主线程执行
            keyboard.add_hotkey('ctrl+space', lambda: QTimer.singleShot(0, self.close_program))
        except Exception as e:
            print(f"注册热键失败: {e}")

        # 用于存储鼠标点击的起始位置
        self.drag_position = QPoint()
        self.is_resizing = False  # 用于控制是否处于调整大小模式

        # 限制最大尺寸
        self.max_width = 2200
        self.max_height = 2200

        # 表情状态变量，初始为expression0
        self.current_expression = 'expression0'
        
        # 设置系统托盘图标
        self.setup_system_tray()

    def setup_system_tray(self):
        """
        设置系统托盘图标和菜单
        """
        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        
        # 设置图标（如果没有图标文件，可以使用临时图标）
        # 尝试使用预览图片作为图标
        preview_path = os.path.join(BASE_DIR, 'preview.png')
        if os.path.exists(preview_path):
            self.tray_icon.setIcon(QIcon(preview_path))
        else:
            # 创建一个简单的红色图标作为默认图标
            from PyQt5.QtGui import QPixmap
            pixmap = QPixmap(24, 24)
            pixmap.fill(QColor(255, 0, 0))
            self.tray_icon.setIcon(QIcon(pixmap))
        
        # 设置托盘图标提示信息
        self.tray_icon.setToolTip("SpacervalLam")
        
        # 创建系统托盘菜单
        self.create_tray_menu()
        
        # 连接托盘图标信号
        self.tray_icon.activated.connect(self.on_tray_activated)
        
        # 显示系统托盘图标
        self.tray_icon.show()
    
    def create_tray_menu(self):
        """
        创建系统托盘右键菜单
        """
        # 创建菜单并使用自定义的FancyMenu类
        self.tray_menu = FancyMenu(self)
        
        # 创建菜单项
        help_action = QAction("使用说明", self)
        help_action.triggered.connect(self.show_help)
        
        expression_action = QAction("切换表情", self)
        expression_action.triggered.connect(self.toggle_expression)
        
        exit_action = QAction("再见", self)
        exit_action.triggered.connect(self.close_program)
        
        # 添加菜单项到菜单
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(expression_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(help_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(exit_action)
        
        # 设置系统托盘菜单
        self.tray_icon.setContextMenu(self.tray_menu)
    
    def on_tray_activated(self, reason):
        """
        系统托盘图标被激活时的处理
        """
        # 不做任何操作，移除双击显示/隐藏的功能
    
    def unregister_hotkeys(self):
        # 注销所有注册的热键
        try:
            keyboard.unhook_all_hotkeys()
        except Exception as e:
            print(f"注销热键失败: {e}")

    def closeEvent(self, event):
        """
        关闭事件，清理资源
        """
        # 在关闭时隐藏系统托盘图标
        if self.tray_icon.isVisible():
            self.tray_icon.hide()
        
        self.unregister_hotkeys()
        live2d.dispose()  # 释放 Live2D 模型资源
        event.accept()

    def check_ctrl_state(self):
        """
        检测CTRL键的状态并相应地更新窗口的鼠标穿透属性
        """
        # 获取当前是否按住CTRL键（使用keyboard库检测，更准确）
        is_ctrl_pressed = keyboard.is_pressed('ctrl')
        
        # 检查是否需要改变穿透状态
        if is_ctrl_pressed and self.is_mouse_transparent:
            # 按住CTRL键，关闭穿透
    
            self.is_mouse_transparent = False
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.apply_mouse_transparency(False)
        elif not is_ctrl_pressed and not self.is_mouse_transparent:
            # 未按住CTRL键，开启穿透
    
            self.is_mouse_transparent = True
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.apply_mouse_transparency(True)
    
    def apply_mouse_transparency(self, transparent):
        """
        应用鼠标穿透设置
        """
        # 获取窗口句柄
        hwnd = int(self.winId())
        # 设置窗口的鼠标穿透属性
        set_window_transparent_for_mouse_events(hwnd, transparent)
    
    def mousePressEvent(self, event):
        """
        捕捉鼠标按下事件，记录当前鼠标的位置
        仅当按住CTRL键时才响应鼠标事件
        """
        # 检查是否按住了CTRL键
        if event.modifiers() == Qt.ControlModifier:
            if event.button() == Qt.LeftButton:
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                self.is_resizing = False  # 按下时不调整大小
                # 通知Live2DWidget按下了CTRL+鼠标
                if hasattr(self, 'live2d_widget'):
                    self.live2d_widget.is_ctrl_mouse_pressed = True

    def mouseMoveEvent(self, event):
        """
        捕捉鼠标移动事件，更新窗口的位置
        仅当按住CTRL键时才响应鼠标事件
        """
        # 检查是否按住了CTRL键
        if event.modifiers() == Qt.ControlModifier:
            if event.buttons() == Qt.LeftButton and not self.is_resizing:
                self.move(event.globalPos() - self.drag_position)
    
    def mouseReleaseEvent(self, event):
        """
        鼠标释放事件
        """
        # 重置调整大小状态
        self.is_resizing = False
        # 通知Live2DWidget释放了鼠标
        if hasattr(self, 'live2d_widget'):
            self.live2d_widget.is_ctrl_mouse_pressed = False
            # 恢复眼睛睁开状态
            self.live2d_widget.target_eye_open = 1.0
            # 恢复嘴巴的正常状态
            self.live2d_widget.target_mouth_open = 0.1

    def wheelEvent(self, event):
        """
        捕捉滚轮事件，用于调整窗口大小
        仅当按住CTRL键时才响应鼠标事件
        """
        # 检查是否按住了CTRL键
        if event.modifiers() == Qt.ControlModifier:
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
            if self.width() < 400 or self.height() < 400:
                self.resize(400, 400)

    def close_program(self):
        """
        关闭程序前先显示离开GIF
        """
        # 隐藏Live2D模型
        if hasattr(self, 'live2d_widget'):
            self.live2d_widget.model = None
            self.live2d_widget.update()
            
        # 创建QLabel显示GIF
        from PyQt5.QtWidgets import QLabel
        from PyQt5.QtGui import QMovie
        from PyQt5.QtCore import QTimer
        
        # 创建标签并设置GIF
        self.gif_label = QLabel(self)
        gif_path = os.path.join(BASE_DIR, 'asset', 'leaving.gif')
        self.movie = QMovie(gif_path)
        self.gif_label.setMovie(self.movie)
        
        # 居中显示GIF
        self.gif_label.setAlignment(Qt.AlignCenter)
        
        gif_height = self.height() - 50
        
        # 加载GIF
        self.movie.jumpToFrame(0)  # 确保GIF已加载
        if self.movie.frameCount() > 0:

            orig_width = self.movie.frameRect().width()
            orig_height = self.movie.frameRect().height()
            
            if orig_height > 0:

                gif_width = int((orig_width / orig_height) * gif_height)
            else:
                gif_width = gif_height
        else:
            gif_width = gif_height
        
        self.gif_label.setGeometry(
            (self.width() - gif_width) // 2 - 2,
            28,  # 垂直顶部对齐
            gif_width,
            gif_height
        )
        
        # 设置GIF自动缩放，但保持原始宽高比
        self.gif_label.setScaledContents(True)
        self.gif_label.show()
        
        # 启动GIF播放
        self.movie.start()
        
        # 4650ms后关闭程序
        QTimer.singleShot(4650, self.actual_close)

    def actual_close(self):
        """
        实际执行关闭程序的操作，释放资源
        """
        # 注销热键
        self.unregister_hotkeys()
        
        # 清理资源
        if self.tray_icon.isVisible():
            self.tray_icon.hide()
        
        try:
            live2d.dispose()  # 释放 Live2D 模型资源
        except:
            pass
        
        # 停止GIF播放
        if hasattr(self, 'movie'):
            self.movie.stop()
        
        # 关闭窗口并退出应用
        self.close()
        QApplication.quit()
        sys.exit()
    
    def contextMenuEvent(self, event):
        """
        捕捉右键点击事件，显示右键菜单
        右键菜单不需要CTRL键也能显示
        美化后的菜单，只保留退出功能
        """
        # 临时禁用鼠标穿透，以显示右键菜单
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.apply_mouse_transparency(False)
        
        # 创建菜单并使用自定义的FancyMenu类
        menu = FancyMenu(self)
        
        # 不再在这里设置样式，因为已经在FancyMenu的构造函数中设置了完整的样式

        # 创建"再见"菜单项（退出功能）
        exit_action = QAction("再见", self)
        exit_action.setIconText("再见")  # 确保图标文本一致
        exit_action.triggered.connect(self.close_program)  # 绑定关闭窗口的槽
        menu.addAction(exit_action)

        # 显示菜单时添加轻微动画效果
        menu.exec_(event.globalPos())
        
        # 恢复鼠标穿透状态
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.apply_mouse_transparency(True)



    def show_help(self):
        """
        显示程序使用说明
        """
        QMessageBox.information(self, "SpacervalLam の 说明",
                                "1.按住CTRL键并滚动鼠标滚轮可以缩放桌宠大小\n\n2.按住CTRL键并拖动可以改变桌宠位置\n\n3.默认情况下鼠标点击会穿透桌宠\n\n4.右键单击系统托盘图标可显示菜单\n\n")



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
    
    # 移除右键菜单事件处理，避免窗口上显示右键菜单
    def contextMenuEvent(self, event):
        """
        重写右键菜单事件，不做任何处理
        """
        pass  # 不显示右键菜单


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Live2DWindow()
    
    sys.exit(app.exec_())
