from pathlib import Path

from .config import load_config, get_current_version, increment_version, update_version
from .logger import setup_logger, log_step, log_separator
from .environment import (
    check_python_version,
    check_dependencies,
    check_git_repo,
    check_pypirc,
    install_build_tools,
    run_command,
)
from .packaging import build_package, check_package, verify_package
from .versioning import (
    create_changelog,
    git_add_all,
    git_commit,
    git_create_tag,
    git_push,
    git_push_tag,
    get_git_status,
)
from .publishing import publish_to_pypi


class ReleaseError(Exception):
    """发布过程中的异常"""
    pass


class ReleaseManager:
    """发布管理器"""
    
    def __init__(self, config=None):
        self.config = config or load_config()
        self.logger = setup_logger(self.config)
        self.project_root = Path(__file__).parent.parent
        self.current_version = None
        self.new_version = None
    
    def confirm_action(self, message):
        """交互式确认操作"""
        if hasattr(sys, 'ps1'):
            response = input(f"\n{message} (y/N): ").strip().lower()
            return response in ["y", "yes"]
        else:
            self.logger.warning("非交互式环境，自动确认")
            return True
    
    def check_environment(self):
        """检查环境"""
        log_step(self.logger, "检查 Python 版本", "running")
        success, msg = check_python_version()
        if not success:
            log_step(self.logger, f"Python 版本检查失败: {msg}", "error")
            return False
        log_step(self.logger, msg, "success")
        
        log_step(self.logger, "检查核心依赖", "running")
        missing = check_dependencies(["fabric", "twine", "build"])
        if missing:
            log_step(self.logger, f"缺少依赖: {', '.join(missing)}", "warning")
            log_step(self.logger, "尝试安装依赖...", "running")
            result = install_build_tools()
            if not result["success"]:
                log_step(self.logger, f"依赖安装失败: {result['stderr']}", "error")
                return False
            log_step(self.logger, "依赖安装成功", "success")
        else:
            log_step(self.logger, "所有核心依赖已安装", "success")
        
        log_step(self.logger, "检查 Git 仓库", "running")
        if not check_git_repo(self.project_root):
            log_step(self.logger, "不是 Git 仓库", "error")
            return False
        log_step(self.logger, "Git 仓库检查通过", "success")
        
        log_step(self.logger, "检查 PyPI 配置", "running")
        exists, path = check_pypirc(self.config)
        if not exists:
            log_step(self.logger, f"PyPI 配置文件不存在: {path}", "warning")
            log_step(self.logger, "请确保已配置 ~/.pypirc 或使用环境变量", "warning")
        else:
            log_step(self.logger, f"PyPI 配置文件: {path}", "success")
        
        return True
    
    def prepare_release(self, bump_level="patch"):
        """准备发布"""
        log_step(self.logger, "获取当前版本", "running")
        self.current_version = get_current_version(self.project_root / self.config["project"]["version_file"])
        if not self.current_version:
            log_step(self.logger, "无法获取当前版本", "error")
            return False
        log_step(self.logger, f"当前版本: {self.current_version}", "success")
        
        log_step(self.logger, f"计算新版本 ({bump_level})", "running")
        self.new_version = increment_version(self.current_version, bump_level)
        log_step(self.logger, f"新版本: {self.new_version}", "success")
        
        if not self.confirm_action(f"确认升级版本: {self.current_version} -> {self.new_version}"):
            log_step(self.logger, "用户取消操作", "error")
            return False
        
        log_step(self.logger, "更新版本文件", "running")
        update_version(self.new_version, self.project_root / self.config["project"]["version_file"])
        log_step(self.logger, "版本文件已更新", "success")
        
        log_step(self.logger, "创建更新日志", "running")
        changelog_dir = self.project_root / self.config["project"]["changelog_dir"]
        changelog_dir.mkdir(exist_ok=True)
        changelog_path = create_changelog(self.new_version, changelog_dir)
        log_step(self.logger, f"更新日志已创建: {changelog_path}", "success")
        
        return True
    
    def run_tests(self):
        """运行测试"""
        if not self.config["testing"]["run_tests"]:
            log_step(self.logger, "测试已跳过", "warning")
            return True
        
        log_step(self.logger, "运行单元测试", "running")
        test_dir = self.project_root / self.config["testing"]["test_dir"]
        result = run_command(f"{self.config['testing']['test_command']} {test_dir} -v", cwd=self.project_root)
        
        if result["success"]:
            log_step(self.logger, "测试通过", "success")
            return True
        else:
            log_step(self.logger, f"测试失败: {result['stderr']}", "error")
            if self.confirm_action("测试失败，是否继续发布？"):
                log_step(self.logger, "用户确认继续", "warning")
                return True
            return False
    
    def build_package(self):
        """构建包"""
        log_step(self.logger, "构建项目包", "running")
        result = build_package(self.project_root, self.config)
        if not result["success"]:
            log_step(self.logger, f"构建失败: {result['stderr']}", "error")
            return False
        log_step(self.logger, "构建成功", "success")
        
        log_step(self.logger, "检查构建产物", "running")
        package_info = check_package(self.project_root, self.config, self.new_version)
        if not package_info["success"]:
            log_step(self.logger, f"缺少构建产物: {package_info['missing']}", "error")
            return False
        log_step(self.logger, f"找到构建产物: {', '.join(package_info['found'])}", "success")
        
        log_step(self.logger, "验证包完整性", "running")
        result = verify_package(self.config)
        if not result["success"]:
            log_step(self.logger, f"包验证失败: {result['stderr']}", "error")
            return False
        log_step(self.logger, "包验证通过", "success")
        
        return True
    
    def version_control(self):
        """版本控制操作"""
        log_step(self.logger, "检查 Git 状态", "running")
        status = get_git_status(self.project_root)
        log_step(self.logger, f"Git 状态: {status['stdout'].strip() or 'clean'}", "success")
        
        if self.config["git"]["create_tag"]:
            log_step(self.logger, "添加变更到 Git", "running")
            result = git_add_all(self.project_root)
            if not result["success"]:
                log_step(self.logger, f"Git add 失败: {result['stderr']}", "error")
                return False
            log_step(self.logger, "变更已添加", "success")
            
            log_step(self.logger, "提交变更", "running")
            message = f"Release v{self.new_version}"
            result = git_commit(self.project_root, message)
            if not result["success"]:
                log_step(self.logger, f"Git commit 失败: {result['stderr']}", "error")
                return False
            log_step(self.logger, "变更已提交", "success")
            
            log_step(self.logger, "创建版本标签", "running")
            result = git_create_tag(self.project_root, self.new_version)
            if not result["success"]:
                log_step(self.logger, f"创建标签失败: {result['stderr']}", "error")
                return False
            log_step(self.logger, f"标签 v{self.new_version} 已创建", "success")
        
        return True
    
    def publish(self, test=False):
        """发布到 PyPI"""
        log_step(self.logger, f"发布到 {'测试' if test else '正式'} PyPI", "running")
        result = publish_to_pypi(self.project_root, self.config, test)
        if not result["success"]:
            log_step(self.logger, f"发布失败: {result['stderr']}", "error")
            return False
        log_step(self.logger, f"发布成功！版本: {self.new_version}", "success")
        log_step(self.logger, f"查看: https://pypi.org/project/{self.config['project']['name']}/{self.new_version}/", "success")
        
        return True
    
    def push_to_github(self):
        """推送到 GitHub"""
        if not self.config["git"]["push_tag"]:
            log_step(self.logger, "跳过推送 GitHub", "warning")
            return True
        
        log_step(self.logger, "推送代码到 GitHub", "running")
        result = git_push(self.project_root, self.config["git"]["remote_name"], self.config["git"]["main_branch"])
        if not result["success"]:
            log_step(self.logger, f"推送代码失败: {result['stderr']}", "error")
            if self.confirm_action("代码推送失败，是否继续推送标签？"):
                pass
            else:
                return False
        else:
            log_step(self.logger, "代码推送成功", "success")
        
        log_step(self.logger, "推送标签到 GitHub", "running")
        result = git_push_tag(self.project_root, self.config["git"]["remote_name"], self.new_version)
        if not result["success"]:
            log_step(self.logger, f"推送标签失败: {result['stderr']}", "error")
            return False
        log_step(self.logger, f"标签 v{self.new_version} 推送成功", "success")
        
        return True
    
    def release(self, bump_level="patch", test=False, skip_tests=False):
        """完整发布流程"""
        log_separator(self.logger)
        self.logger.info(f"🚀 开始发布流程 - {self.config['project']['name']}")
        log_separator(self.logger)
        
        try:
            if not self.check_environment():
                raise ReleaseError("环境检查失败")
            
            if skip_tests:
                self.config["testing"]["run_tests"] = False
            
            if not self.prepare_release(bump_level):
                raise ReleaseError("准备发布失败")
            
            if not self.run_tests():
                raise ReleaseError("测试失败")
            
            if not self.build_package():
                raise ReleaseError("构建失败")
            
            if not self.version_control():
                raise ReleaseError("版本控制失败")
            
            if not self.confirm_action(f"确认发布 v{self.new_version} 到 PyPI？"):
                raise ReleaseError("用户取消发布")
            
            if not self.publish(test):
                raise ReleaseError("发布失败")
            
            if not self.push_to_github():
                log_step(self.logger, "GitHub 推送失败，但包已发布", "warning")
            
            log_separator(self.logger)
            self.logger.info(f"🎉 发布完成！版本 {self.new_version} 已成功发布")
            log_separator(self.logger)
            
            return True
            
        except ReleaseError as e:
            log_separator(self.logger)
            self.logger.error(f"❌ 发布失败: {str(e)}")
            log_separator(self.logger)
            return False
        except Exception as e:
            log_separator(self.logger)
            self.logger.error(f"❌ 发布过程发生异常: {str(e)}", exc_info=True)
            log_separator(self.logger)
            return False
