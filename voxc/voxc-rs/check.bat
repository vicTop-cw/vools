@echo off
cd /d e:\IDEProjects\AI\vools\voxc\voxc-rs
set CARGO_TARGET_DIR=e:\IDEProjects\AI\vools\voxc\voxc-rs\target4
cargo check --release 2>&1
echo CARGO_EXIT:%errorlevel%
