use clap::{Parser, Subcommand};
use std::path::PathBuf;

mod ast;
mod cli;
mod codegen;
mod transform;

#[derive(Parser)]
#[command(name = "voxc")]
#[command(about = "Vox language compiler (Rust backend)")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Compile: read AST JSON from stdin, generate Rust code, write to __vox_rust_cache__/
    Compile {
        /// Path to the .vox source file (used to determine output directory)
        #[arg(short, long)]
        input: PathBuf,
        /// AST JSON input (read from stdin if not provided)
        #[arg(short, long)]
        ast_json: Option<PathBuf>,
    },
    /// Run: compile then invoke rustc + run
    Run {
        #[arg(short, long)]
        input: PathBuf,
        #[arg(short, long)]
        ast_json: Option<PathBuf>,
    },
    /// Dump AST: read and display AST JSON
    Ast {
        #[arg(short, long)]
        ast_json: PathBuf,
    },
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Command::Compile { input, ast_json } => {
            cli::compile(&input, ast_json.as_ref())?;
        }
        Command::Run { input, ast_json } => {
            cli::compile_and_run(&input, ast_json.as_ref())?;
        }
        Command::Ast { ast_json } => {
            cli::dump_ast(&ast_json)?;
        }
    }

    Ok(())
}