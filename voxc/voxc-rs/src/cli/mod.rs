use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::ast::Module;
use crate::codegen::RustCodegen;

/// Compile: read AST JSON, generate Rust code, write to __vox_rust_cache__/
pub fn compile(input: &Path, ast_json: Option<&PathBuf>) -> anyhow::Result<()> {
    // Read AST JSON
    let ast_json_str = match ast_json {
        Some(path) => fs::read_to_string(path)?,
        None => {
            // Read from stdin
            let mut buf = String::new();
            std::io::Read::read_to_string(&mut std::io::stdin(), &mut buf)?;
            buf
        }
    };

    // Parse AST
    let module: Module = serde_json::from_str(&ast_json_str)?;

    // Generate Rust code
    let mut codegen = RustCodegen::new();
    // Read source code for inspect module
    let source_code = fs::read_to_string(input).unwrap_or_default();
    let source_file = input.to_string_lossy().to_string();
    codegen = codegen.with_source(&source_code, &source_file);
    let rust_code = codegen.generate(&module);

    // Determine output directory: __vox_rust_cache__/ next to the .vox file
    let vox_dir = input.parent().unwrap_or(Path::new("."));
    let cache_dir = vox_dir.join("__vox_rust_cache__");
    let src_dir = cache_dir.join("src");

    fs::create_dir_all(&src_dir)?;

    // Write Cargo.toml — use transtime directives if present
    let cargo_toml = cache_dir.join("Cargo.toml");
    let transtime = codegen.get_transtime_output();
    let cargo_content = generate_cargo_toml(
        &input.file_stem().unwrap_or_default().to_string_lossy(),
        transtime,
    );
    fs::write(&cargo_toml, cargo_content)?;

    // Write main.rs
    let main_rs = src_dir.join("main.rs");
    fs::write(&main_rs, &rust_code)?;

    // Write source map for tracker
    let voxmap = codegen.generate_source_map();
    let voxmap_path = src_dir.join("main.voxmap");
    fs::write(&voxmap_path, &voxmap)?;

    // Write extra files from transtime directives
    for (filename, content) in &transtime.extra_files {
        let file_path = src_dir.join(filename);
        fs::write(&file_path, content)?;
        eprintln!("Transtime file: {}", file_path.display());
    }

    eprintln!("Generated: {}", main_rs.display());
    eprintln!("Cache dir: {}", cache_dir.display());
    eprintln!("Hint: add __vox_rust_cache__/ to .gitignore");

    Ok(())
}

/// Generate Cargo.toml from transtime directives
fn generate_cargo_toml(name: &str, transtime: &crate::codegen::TranstimeOutput) -> String {
    let mut content = String::new();
    content.push_str("[package]\n");
    content.push_str(&format!("name = \"{}\"\n", name));
    content.push_str("version = \"0.1.0\"\n");
    content.push_str("edition = \"2021\"\n");

    // Extra config from transtime — skip keys already in the template
    let reserved: &[&str] = &["name", "version", "edition"];
    for (key, value) in &transtime.config {
        if reserved.contains(&key.as_str()) {
            continue;
        }
        // Handle list values (e.g., authors = ["vox"])
        if value.starts_with('[') {
            content.push_str(&format!("{} = {}\n", key, value));
        } else {
            content.push_str(&format!("{} = \"{}\"\n", key, value));
        }
    }

    content.push_str("\n[dependencies]\n");

    // Dependencies from transtime
    for (crate_name, version) in &transtime.dependencies {
        // Check if there are features for this crate
        let features: Vec<&String> = transtime.features.iter()
            .filter(|(name, _)| name == crate_name)
            .flat_map(|(_, feats)| feats.iter())
            .collect();
        if features.is_empty() {
            content.push_str(&format!("{} = \"{}\"\n", crate_name, version));
        } else {
            let feats_str: Vec<String> = features.iter().map(|f| format!("\"{}\"", f)).collect();
            content.push_str(&format!("{} = {{ version = \"{}\", features = [{}] }}\n",
                crate_name, version, feats_str.join(", ")));
        }
    }

    content
}

/// Compile and run with tracker error mapping
pub fn compile_and_run(input: &Path, ast_json: Option<&PathBuf>) -> anyhow::Result<()> {
    compile(input, ast_json)?;

    let vox_dir = input.parent().unwrap_or(Path::new("."));
    let cache_dir = vox_dir.join("__vox_rust_cache__");
    let voxmap_path = cache_dir.join("src").join("main.voxmap");
    let source_map = load_source_map(&voxmap_path);

    // Run cargo build and capture output
    let output = Command::new("cargo")
        .args(["build", "--release"])
        .current_dir(&cache_dir)
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        // Map rustc errors to Vox source locations
        map_and_print_errors(&stderr, &source_map, input);
        anyhow::bail!("cargo build failed (see mapped errors above)");
    }

    // Run the executable
    let exe_name = if cfg!(windows) {
        format!("{}.exe", input.file_stem().unwrap_or_default().to_string_lossy())
    } else {
        input.file_stem().unwrap_or_default().to_string_lossy().to_string()
    };
    let exe_path = cache_dir.join("target").join("release").join(&exe_name);

    let status = Command::new(&exe_path).status()?;
    if !status.success() {
        anyhow::bail!("program exited with error (panic hook will show Vox source location)");
    }

    Ok(())
}

/// Source map entry: rust_line -> (vox_file, vox_line)
type SourceMap = Vec<(usize, String, usize)>;

/// Load source map from .voxmap file
fn load_source_map(path: &Path) -> SourceMap {
    let content = fs::read_to_string(path).unwrap_or_default();
    let mut map = Vec::new();
    for line in content.lines() {
        if line.starts_with('#') || line.trim().is_empty() {
            continue;
        }
        let parts: Vec<&str> = line.splitn(3, ':').collect();
        if parts.len() == 3 {
            if let (Ok(rust_line), vox_file, Ok(vox_line)) = (
                parts[0].parse::<usize>(),
                parts[1],
                parts[2].parse::<usize>(),
            ) {
                map.push((rust_line, vox_file.to_string(), vox_line));
            }
        }
    }
    map
}

/// Map rustc errors to Vox source locations
fn map_and_print_errors(stderr: &str, source_map: &SourceMap, vox_input: &Path) {
    let vox_dir = vox_input.parent().unwrap_or(Path::new("."));
    let vox_filename = vox_input.file_name().unwrap_or_default().to_string_lossy().to_string();

    for line in stderr.lines() {
        // Check for error/warning location: --> src\main.rs:LINE:COL
        if line.contains("-->") && line.contains("main.rs") {
            // Extract line number
            if let Some(rust_line) = extract_rust_line(line) {
                if let Some((vox_file, vox_line)) = lookup_vox_position(source_map, rust_line) {
                    let display_file = if vox_file.is_empty() {
                        &vox_filename
                    } else {
                        vox_file
                    };
                    let source_line = read_vox_source_line(vox_dir, display_file, vox_line);
                    eprintln!("  --> {}:{}  {}", display_file, vox_line, source_line);
                } else {
                    eprintln!("{}", line);
                }
            } else {
                eprintln!("{}", line);
            }
        } else {
            eprintln!("{}", line);
        }
    }
}

/// Extract rust line number from error output
fn extract_rust_line(line: &str) -> Option<usize> {
    // Format: --> src\main.rs:33:5  or  --> src/main.rs:33:5
    let line = line.trim();
    let after_arrow = line.split("-->").nth(1)?;
    let after_rs = after_arrow.split("main.rs").nth(1)?;
    let line_col: Vec<&str> = after_rs.trim_start_matches(':').split(':').collect();
    let line_num = line_col.first()?.parse::<usize>().ok()?;
    Some(line_num)
}

/// Look up Vox source position from Rust line number
fn lookup_vox_position(source_map: &SourceMap, rust_line: usize) -> Option<(&str, usize)> {
    // Find the closest matching entry (exact or nearest below)
    let mut best: Option<(&str, usize)> = None;
    for (rl, vf, vl) in source_map {
        if *rl == rust_line && !vf.is_empty() {
            return Some((vf, *vl));
        }
        if *rl <= rust_line && !vf.is_empty() {
            best = Some((vf, *vl));
        }
    }
    best
}

/// Read a specific line from the Vox source file
fn read_vox_source_line(vox_dir: &Path, filename: &str, line_num: usize) -> String {
    let path = vox_dir.join(filename);
    if let Ok(content) = fs::read_to_string(&path) {
        let lines: Vec<&str> = content.lines().collect();
        if line_num > 0 && line_num <= lines.len() {
            return lines[line_num - 1].trim().to_string();
        }
    }
    String::new()
}

/// Dump AST JSON for debugging
pub fn dump_ast(ast_json: &Path) -> anyhow::Result<()> {
    let content = fs::read_to_string(ast_json)?;
    // Pretty-print
    let parsed: serde_json::Value = serde_json::from_str(&content)?;
    let pretty = serde_json::to_string_pretty(&parsed)?;
    println!("{}", pretty);
    Ok(())
}