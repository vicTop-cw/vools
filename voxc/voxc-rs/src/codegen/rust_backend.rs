use crate::ast::*;
use std::collections::{HashSet, HashMap};

/// Function metadata for inspect/reflect
#[derive(Debug, Clone)]
struct FnMeta {
    name: String,
    params: Vec<FnParam>,
    return_type: Option<Type>,
    span: Span,
}

/// Field pointer strategy for self-referential types
#[derive(Debug, Clone, PartialEq)]
enum PtrStrategy {
    Box,        // default: Option<Box<T>>
    Arc,        // @arc: Option<Arc<Mutex<T>>>
    Rc,         // @rc:  Option<Rc<RefCell<T>>>
    Raw,        // @raw: *mut T (unsafe)
}

/// Type metadata for reflect
#[derive(Debug, Clone)]
struct TypeMeta {
    name: String,
    kind: TypeKind,
    fields: Vec<StructField>,
    variants: Vec<EnumVariant>,
    methods: Vec<String>,
    /// Map of field name → pointer strategy (for self-referential fields)
    field_ptrs: HashMap<String, PtrStrategy>,
    /// Set of field names that are self-referential
    self_ref_fields: HashSet<String>,
}

#[derive(Debug, Clone, PartialEq)]
enum TypeKind {
    Struct,
    Enum,
    Class,
    Trait,
}

/// Transtime directives collected from transtime blocks
#[derive(Debug, Clone, Default)]
pub struct TranstimeOutput {
    pub dependencies: Vec<(String, String)>,
    pub features: Vec<(String, Vec<String>)>,
    pub extra_files: Vec<(String, String)>,
    pub config: Vec<(String, String)>,
}

/// Rust code generation backend
pub struct RustCodegen {
    indent_level: usize,
    output: String,
    struct_types: HashSet<String>,
    enum_types: HashSet<String>,
    struct_fields: HashMap<String, Vec<String>>,
    enum_variants: HashMap<String, Vec<String>>,
    var_types: HashMap<String, String>,
    lazy_vars: HashSet<String>,
    fn_metadata: HashMap<String, FnMeta>,
    type_metadata: HashMap<String, TypeMeta>,
    /// Doc strings keyed by type/function name (for inspect.doc / reflect.doc)
    doc_registry: HashMap<String, String>,
    /// Track impl blocks: type_name → list of (trait_name, ...)
    impl_traits: HashMap<String, Vec<String>>,
    source_code: String,
    source_file: String,
    transtime: TranstimeOutput,
    /// Source map entry: rust_line -> (vox_file, vox_line)
    source_map: Vec<(usize, String, usize)>,
    /// Current Vox source position being generated from
    current_vox_file: String,
    current_vox_line: usize,
    /// Rust output line counter (1-based)
    rust_line_counter: usize,
    /// Statements to be placed inside main()
    main_statements: Vec<Stmt>,
    /// Track which stdlib modules have been used (for emitting helper code)
    modules_used: HashSet<String>,
    /// Set of stdlib modules referenced in the source (time, datetime, copy, weakref)
    used_stdlib_modules: HashSet<String>,
    /// Whether a monotonic time base static is needed (perf_counter / monotonic)
    needs_time_base: bool,
    /// Whether the chrono crate dependency is needed
    needs_chrono: bool,
    /// Whether the random stdlib module is used (drives `rand` crate import + dep)
    uses_random: bool,
    /// Whether math/cmath/decimals/fractions helper structs are needed
    uses_math_helpers: bool,
}

impl RustCodegen {
    pub fn new() -> Self {
        RustCodegen {
            indent_level: 0,
            output: String::new(),
            struct_types: HashSet::new(),
            enum_types: HashSet::new(),
            struct_fields: HashMap::new(),
            enum_variants: HashMap::new(),
            var_types: HashMap::new(),
            lazy_vars: HashSet::new(),
            fn_metadata: HashMap::new(),
            type_metadata: HashMap::new(),
            doc_registry: HashMap::new(),
            impl_traits: HashMap::new(),
            source_code: String::new(),
            source_file: String::new(),
            transtime: TranstimeOutput::default(),
            source_map: Vec::new(),
            current_vox_file: String::new(),
            current_vox_line: 0,
            rust_line_counter: 0,
            main_statements: Vec::new(),
            modules_used: HashSet::new(),
            used_stdlib_modules: HashSet::new(),
            needs_time_base: false,
            needs_chrono: false,
            uses_random: false,
            uses_math_helpers: false,
        }
    }

    pub fn with_source(mut self, source: &str, file: &str) -> Self {
        self.source_code = source.to_string();
        self.source_file = file.to_string();
        self
    }

    /// Generate source map content as a string
    pub fn generate_source_map(&self) -> String {
        let mut content = String::new();
        content.push_str("# Vox Source Map — auto-generated, do not edit\n");
        content.push_str("# format: rust_line:vox_file:vox_line\n");
        for (rust_line, vox_file, vox_line) in &self.source_map {
            content.push_str(&format!("{}:{}:{}\n", rust_line, vox_file, vox_line));
        }
        content
    }

    /// Generate embedded source map for panic hook
    fn generate_embedded_source_map(&self) -> String {
        let mut entries: Vec<String> = Vec::new();
        for (rust_line, vox_file, vox_line) in &self.source_map {
            entries.push(format!("{},{},{}", rust_line, vox_file, vox_line));
        }
        entries.join(";")
    }

    fn escape_for_rust_string(&self, s: &str) -> String {
        s.replace('\\', "\\\\")
         .replace('"', "\\\"")
    }

    /// Get the source map for external use (CLI tracker)
    pub fn get_source_map(&self) -> &[(usize, String, usize)] {
        &self.source_map
    }

    /// Get transtime output for Cargo.toml and extra files
    pub fn get_transtime_output(&self) -> &TranstimeOutput {
        &self.transtime
    }

    pub fn generate(&mut self, module: &Module) -> String {
        self.collect_metadata(module);
        self.collect_transtime(module);
        self.scan_stdlib_usage(module);
        self.emit_line("// Generated by Vox compiler — do not edit manually");
        self.emit_line("");

        // Emit use statements
        self.emit_line("use std::io::{self, Write};");
        self.emit_line("use std::collections::{HashMap, HashSet};");
        self.emit_line("use std::panic;");
        // Conditionally emit rand imports when the random module is used.
        if self.uses_random {
            self.emit_line("use rand::Rng;");
            self.emit_line("use rand::seq::SliceRandom;");
        }
        // Conditionally emit a monotonic time base static for time.perf_counter /
        // time.monotonic / time.process_time family.
        if self.needs_time_base {
            self.emit_line("static VOX_TIME_BASE: std::sync::LazyLock<std::time::Instant> = std::sync::LazyLock::new(std::time::Instant::now);");
        }
        self.emit_line("");
        self.emit_line("/* VOX_SOURCE_MAP_PLACEHOLDER */");
        self.emit_line("");

        // Panic hook — maps runtime errors back to Vox source
        self.emit_raw(&format!(r#"fn vox_install_panic_hook() {{
    panic::set_hook(Box::new(|info| {{
        eprintln!("=== Vox Runtime Error ===");
        if let Some(loc) = info.location() {{
            let rust_line = loc.line() as usize;
            eprintln!("  Rust: {{}}:{{}}:{{}}", loc.file(), rust_line, loc.column());
            let mut found = false;
            for entry in VOX_SOURCE_MAP.split(';') {{
                let parts: Vec<&str> = entry.split(',').collect();
                if parts.len() == 3 {{
                    if let Ok(rl) = parts[0].parse::<usize>() {{
                        if rl == rust_line && !parts[1].is_empty() {{
                            if let Ok(vl) = parts[2].parse::<usize>() {{
                                eprintln!("  Vox:  {{}}:{{}}", parts[1], vl);
                                found = true;
                            }}
                        }}
                    }}
                }}
            }}
            if !found {{
                eprintln!("  Vox:  (no source map entry for this line)");
            }}
        }} else {{
            eprintln!("  (no location info)");
        }}
        eprintln!("  Message: {{}}", info);
        eprintln!("========================");
    }}));
}}
"#));

        // Emit logging support structs (always — small and harmless)
        self.emit_logging_support();

        // Emit math/cmath/decimals/fractions helper structs (only if used)
        if self.uses_math_helpers {
            self.emit_stdlib_helpers();
        }

        // Vox introspection helper functions
        self.emit_line("");
        self.emit_raw(r#"// Vox introspection helpers
fn vox_dir<T>(_x: &T) -> Vec<String> {
    let tn = std::any::type_name::<T>();
    if tn == "alloc::string::String" {
        vec!["len".into(), "is_empty".into(), "push".into(), "pop".into(),
             "push_str".into(), "clear".into(), "as_str".into(), "chars".into(),
             "bytes".into(), "to_string".into()]
    } else if tn.starts_with("alloc::vec::Vec") {
        vec!["len".into(), "is_empty".into(), "push".into(), "pop".into(),
             "clear".into(), "extend".into(), "iter".into(), "first".into(),
             "last".into(), "get".into()]
    } else if matches!(tn, "i8"|"i16"|"i32"|"i64"|"i128"|"isize"|
                           "u8"|"u16"|"u32"|"u64"|"u128"|"usize"|
                           "f32"|"f64") {
        vec!["abs".into(), "pow".into(), "to_string".into(),
             "min".into(), "max".into()]
    } else if tn == "bool" {
        vec!["to_string".into(), "then".into(), "then_some".into()]
    } else {
        vec!["to_string".into(), "type_name".into(), "eq".into(), "ne".into()]
    }
}

fn vox_help<T>(x: &T) -> String {
    let tn = std::any::type_name::<T>();
    let methods = vox_dir(x);
    format!("Help on {}\nMethods: {}\n", tn, methods.join(", "))
}

fn vox_id<T>(x: &T) -> usize {
    let p: *const T = x;
    p as usize
}

fn vox_hash<T: std::hash::Hash>(x: &T) -> u64 {
    use std::hash::Hasher;
    use std::collections::hash_map::DefaultHasher;
    let mut h = DefaultHasher::new();
    std::hash::Hash::hash(x, &mut h);
    h.finish()
}

fn vox_isinstance<T>(_x: &T, type_name: &str) -> bool {
    let actual = std::any::type_name::<T>();
    actual == type_name || actual.ends_with(type_name)
}
"#);
        self.emit_line("");

        // Emit module body - separate into module-level and main-level
        for stmt in &module.statements {
            match stmt {
                Stmt::VarDecl { .. } | Stmt::ExprStmt { .. } | Stmt::IfStmt { .. } |
                Stmt::WhileLoop { .. } | Stmt::ForLoop { .. } | Stmt::LoopStmt { .. } |
                Stmt::MatchStmt { .. } | Stmt::ReturnStmt { .. } | Stmt::BreakStmt { .. } |
                Stmt::ContinueStmt { .. } | Stmt::TryBlock { .. } | Stmt::RaiseStmt { .. } |
                Stmt::DeferStmt { .. } | Stmt::GuardStmt { .. } | Stmt::AssignStmt { .. } |
                Stmt::WhenStmt { .. } => {
                    self.main_statements.push(stmt.clone());
                }
                _ => {
                    self.gen_stmt(stmt);
                }
            }
        }

        // Emit main if not present
        if !self.has_main(&module.statements) {
            self.emit_line("");
            self.emit_line("fn main() {");
            self.indent_level += 1;
            self.emit_line("vox_install_panic_hook();");
            let main_stmts = std::mem::take(&mut self.main_statements);
            if main_stmts.is_empty() {
                self.emit_line("println!(\"Hello from Vox!\");");
            } else {
                for stmt in main_stmts {
                    self.gen_stmt(&stmt);
                }
            }
            self.indent_level -= 1;
            self.emit_line("}");
        }

        // Emit reflect metadata (runtime trait impls)
        self.emit_reflect_metadata();

        // Emit doc registry (for inspect.doc / reflect.doc runtime lookup)
        self.emit_doc_registry();

        // Now replace the placeholder with the actual source map
        let embedded_map = self.generate_embedded_source_map();
        let map_str = format!(
            "static VOX_SOURCE_MAP: &str = \"{}\";",
            self.escape_for_rust_string(&embedded_map)
        );
        let final_output = self.output.replace("/* VOX_SOURCE_MAP_PLACEHOLDER */", &map_str);

        final_output
    }

    fn has_main(&self, stmts: &[Stmt]) -> bool {
        stmts.iter().any(|s| matches!(s, Stmt::FnDef { name, .. } if name == "main"))
    }

    fn collect_metadata(&mut self, module: &Module) {
        for stmt in &module.statements {
            match stmt {
                Stmt::StructDef { name, fields, doc, .. } => {
                    self.struct_types.insert(name.clone());
                    let field_names: Vec<String> = fields.iter().map(|f| f.name.clone()).collect();
                    self.struct_fields.insert(name.clone(), field_names);
                    self.type_metadata.insert(name.clone(), TypeMeta {
                        name: name.clone(),
                        kind: TypeKind::Struct,
                        fields: fields.clone(),
                        variants: vec![],
                        methods: vec![],
                        field_ptrs: HashMap::new(),
                        self_ref_fields: HashSet::new(),
                    });
                    if let Some(d) = doc {
                        self.doc_registry.insert(name.clone(), d.clone());
                    }
                }
                Stmt::EnumDef { name, variants, doc, .. } => {
                    self.enum_types.insert(name.clone());
                    let variant_names: Vec<String> = variants.iter().map(|v| v.name.clone()).collect();
                    self.enum_variants.insert(name.clone(), variant_names);
                    self.type_metadata.insert(name.clone(), TypeMeta {
                        name: name.clone(),
                        kind: TypeKind::Enum,
                        fields: vec![],
                        variants: variants.clone(),
                        methods: vec![],
                        field_ptrs: HashMap::new(),
                        self_ref_fields: HashSet::new(),
                    });
                    if let Some(d) = doc {
                        self.doc_registry.insert(name.clone(), d.clone());
                    }
                }
                Stmt::FnDef { name, params, return_type, span, doc, .. } => {
                    self.fn_metadata.insert(name.clone(), FnMeta {
                        name: name.clone(),
                        params: params.clone(),
                        return_type: return_type.clone(),
                        span: span.clone(),
                    });
                    if let Some(d) = doc {
                        self.doc_registry.insert(name.clone(), d.clone());
                    }
                }
                Stmt::ClassDef { name, fields, methods, doc, .. } => {
                    let method_names: Vec<String> = methods.iter()
                        .filter_map(|m| {
                            if let Stmt::FnDef { name, .. } = m {
                                Some(name.clone())
                            } else {
                                None
                            }
                        })
                        .collect();
                    self.type_metadata.insert(name.clone(), TypeMeta {
                        name: name.clone(),
                        kind: TypeKind::Class,
                        fields: fields.iter().map(|f| StructField {
                            name: f.name.clone(),
                            type_annotation: f.type_annotation.clone().unwrap_or_else(|| Type::Named {
                                span: Span::unknown(),
                                name: "int".to_string(),
                            }),
                        }).collect(),
                        variants: vec![],
                        methods: method_names,
                        field_ptrs: HashMap::new(),
                        self_ref_fields: HashSet::new(),
                    });
                    if let Some(d) = doc {
                        self.doc_registry.insert(name.clone(), d.clone());
                    }
                }
                Stmt::TraitDef { name, methods, doc, .. } => {
                    let method_names: Vec<String> = methods.iter().map(|m| m.name.clone()).collect();
                    self.type_metadata.insert(name.clone(), TypeMeta {
                        name: name.clone(),
                        kind: TypeKind::Trait,
                        fields: vec![],
                        variants: vec![],
                        methods: method_names,
                        field_ptrs: HashMap::new(),
                        self_ref_fields: HashSet::new(),
                    });
                    if let Some(d) = doc {
                        self.doc_registry.insert(name.clone(), d.clone());
                    }
                }
                Stmt::ImplBlock { trait_name, type_name, .. } => {
                    if let Some(trait_name) = trait_name {
                        self.impl_traits.entry(type_name.clone())
                            .or_default()
                            .push(trait_name.clone());
                    }
                }
                _ => {}
            }
        }
        // After all types are collected, detect self-references
        self.detect_self_references();
        // Scan for stdlib module usage (time, datetime, copy, weakref)
        self.scan_stdlib_usage(module);
        // Register chrono dependency if needed
        if self.needs_chrono {
            let has_chrono = self.transtime.dependencies.iter()
                .any(|(name, _)| name == "chrono");
            if !has_chrono {
                self.transtime.dependencies.push(("chrono".to_string(), "0.4".to_string()));
            }
        }
    }

    /// Detect self-referential fields and determine pointer strategy
    fn detect_self_references(&mut self) {
        let type_names: Vec<String> = self.type_metadata.keys().cloned().collect();
        for type_name in &type_names {
            let meta = self.type_metadata.get(type_name).cloned();
            if let Some(meta) = meta {
                let mut self_ref = HashSet::new();
                let mut ptrs = HashMap::new();
                for field in &meta.fields {
                    let field_type = &field.type_annotation;
                    // Check if this field's type references the current type
                    if self.type_references(type_name, field_type) {
                        self_ref.insert(field.name.clone());
                        // Default to Box strategy
                        ptrs.insert(field.name.clone(), PtrStrategy::Box);
                    }
                }
                if let Some(m) = self.type_metadata.get_mut(type_name) {
                    m.self_ref_fields = self_ref;
                    m.field_ptrs = ptrs;
                }
            }
        }
    }

    /// Check if a type annotation references the given type name
    fn type_references(&self, type_name: &str, ty: &Type) -> bool {
        match ty {
            Type::Named { name, .. } => name == type_name,
            Type::Optional { inner, .. } => self.type_references(type_name, inner),
            Type::List { inner, .. } => self.type_references(type_name, inner),
            Type::Generic { args, .. } => args.iter().any(|a| self.type_references(type_name, a)),
            Type::Tuple { types, .. } => types.iter().any(|t| self.type_references(type_name, t)),
            _ => false,
        }
    }

    /// Scan statements for stdlib module calls (time/datetime/copy/weakref)
    /// to track which modules are used and which dependencies are required.
    /// Note: the top-level entry point is `scan_stdlib_usage` (defined later);
    /// these walkers populate `used_stdlib_modules`, `needs_time_base`, `needs_chrono`.
    fn scan_stmt_for_stdlib(&mut self, stmt: &Stmt) {
        match stmt {
            Stmt::VarDecl { value, .. } | Stmt::ConstDecl { value, .. } |
            Stmt::LazyDecl { value, .. } | Stmt::ReturnStmt { value: Some(value), .. } => {
                self.scan_expr_for_stdlib(value);
            }
            Stmt::ExprStmt { expr, .. } | Stmt::DeferStmt { expr, .. } |
            Stmt::RaiseStmt { expr, .. } => {
                self.scan_expr_for_stdlib(expr);
            }
            Stmt::ReturnStmt { value: None, .. } => {}
            Stmt::AssignStmt { target, value, .. } => {
                self.scan_expr_for_stdlib(target);
                self.scan_expr_for_stdlib(value);
            }
            Stmt::FnDef { body, .. } | Stmt::TestStmt { body, .. } |
            Stmt::SuiteStmt { body, .. } | Stmt::ComptimeBlock { body, .. } |
            Stmt::TranstimeBlock { body, .. } => {
                for s in body {
                    self.scan_stmt_for_stdlib(s);
                }
            }
            Stmt::IfStmt { condition, then_body, elif_chain, else_body, .. } => {
                self.scan_expr_for_stdlib(condition);
                for s in then_body {
                    self.scan_stmt_for_stdlib(s);
                }
                for (cond, body) in elif_chain {
                    self.scan_expr_for_stdlib(cond);
                    for s in body {
                        self.scan_stmt_for_stdlib(s);
                    }
                }
                if let Some(else_b) = else_body {
                    for s in else_b {
                        self.scan_stmt_for_stdlib(s);
                    }
                }
            }
            Stmt::MatchStmt { expr, arms, .. } => {
                self.scan_expr_for_stdlib(expr);
                for arm in arms {
                    if let Some(g) = &arm.guard {
                        self.scan_expr_for_stdlib(g);
                    }
                    for s in &arm.body {
                        self.scan_stmt_for_stdlib(s);
                    }
                }
            }
            Stmt::ForLoop { iterable, guard, body, .. } => {
                self.scan_expr_for_stdlib(iterable);
                if let Some(g) = guard {
                    self.scan_expr_for_stdlib(g);
                }
                for s in body {
                    self.scan_stmt_for_stdlib(s);
                }
            }
            Stmt::WhileLoop { condition, body, .. } => {
                self.scan_expr_for_stdlib(condition);
                for s in body {
                    self.scan_stmt_for_stdlib(s);
                }
            }
            Stmt::LoopStmt { body, .. } => {
                for s in body {
                    self.scan_stmt_for_stdlib(s);
                }
            }
            Stmt::TryBlock { try_body, catch_clauses, else_body, finally_body, .. } => {
                for s in try_body {
                    self.scan_stmt_for_stdlib(s);
                }
                for clause in catch_clauses {
                    for s in &clause.body {
                        self.scan_stmt_for_stdlib(s);
                    }
                }
                if let Some(eb) = else_body {
                    for s in eb {
                        self.scan_stmt_for_stdlib(s);
                    }
                }
                if let Some(fb) = finally_body {
                    for s in fb {
                        self.scan_stmt_for_stdlib(s);
                    }
                }
            }
            Stmt::GuardStmt { expr, else_body, .. } => {
                self.scan_expr_for_stdlib(expr);
                for s in else_body {
                    self.scan_stmt_for_stdlib(s);
                }
            }
            Stmt::ClassDef { methods, .. } | Stmt::ImplBlock { methods, .. } |
            Stmt::ExtendDecl { methods, .. } => {
                for m in methods {
                    self.scan_stmt_for_stdlib(m);
                }
            }
            Stmt::WhenStmt { expr, branches, else_body, .. } => {
                self.scan_expr_for_stdlib(expr);
                for b in branches {
                    self.scan_expr_for_stdlib(&b.condition);
                }
                for s in else_body {
                    self.scan_stmt_for_stdlib(s);
                }
            }
            Stmt::DecoratedStmt { stmt, .. } => {
                self.scan_stmt_for_stdlib(stmt);
            }
            _ => {}
        }
    }

    fn scan_expr_for_stdlib(&mut self, expr: &Expr) {
        match expr {
            Expr::MethodCall { receiver, method, args, .. } => {
                // Detect stdlib module calls: time.xxx(), datetime.xxx(), etc.
                if let Expr::Ident { name, .. } = receiver.as_ref() {
                    if matches!(name.as_str(), "time" | "datetime" | "copy" | "weakref") {
                        self.used_stdlib_modules.insert(name.clone());
                        // Determine special requirements
                        match name.as_str() {
                            "time" => {
                                if matches!(method.as_str(), "perf_counter" | "perf_counter_ns" | "monotonic" | "monotonic_ns") {
                                    self.needs_time_base = true;
                                }
                                if matches!(method.as_str(), "ctime" | "strftime" | "localtime" | "gmtime" | "mktime") {
                                    self.needs_chrono = true;
                                }
                            }
                            "datetime" => {
                                self.needs_chrono = true;
                            }
                            _ => {}
                        }
                    }
                    // The random module requires the `rand` crate dependency.
                    if name == "random" {
                        self.uses_random = true;
                        let has_rand = self.transtime.dependencies.iter()
                            .any(|(n, _)| n == "rand");
                        if !has_rand {
                            self.transtime.dependencies.push(("rand".to_string(), "0.8".to_string()));
                        }
                    }
                }
                self.scan_expr_for_stdlib(receiver);
                for a in args {
                    self.scan_expr_for_stdlib(a);
                }
            }
            Expr::Call { func, args, .. } => {
                self.scan_expr_for_stdlib(func);
                for a in args {
                    self.scan_expr_for_stdlib(a);
                }
            }
            Expr::BinaryOp { left, right, .. } => {
                self.scan_expr_for_stdlib(left);
                self.scan_expr_for_stdlib(right);
            }
            Expr::UnaryOp { operand, .. } => self.scan_expr_for_stdlib(operand),
            Expr::Attribute { target, name, .. } => {
                // Detect stdlib module constant access: math.pi, cmath.j, etc.
                if let Expr::Ident { name: mod_name, .. } = target.as_ref() {
                    if matches!(mod_name.as_str(), "math" | "cmath" | "numbers" | "decimals" | "fractions") {
                        self.used_stdlib_modules.insert(mod_name.clone());
                        if matches!(mod_name.as_str(), "cmath" | "decimals" | "fractions") {
                            self.uses_math_helpers = true;
                        }
                    }
                }
                let _ = name;
                self.scan_expr_for_stdlib(target);
            }
            Expr::Index { target, index, .. } => {
                self.scan_expr_for_stdlib(target);
                self.scan_expr_for_stdlib(index);
            }
            Expr::Slice { target, start, end, step, .. } => {
                self.scan_expr_for_stdlib(target);
                if let Some(s) = start { self.scan_expr_for_stdlib(s); }
                if let Some(e) = end { self.scan_expr_for_stdlib(e); }
                if let Some(s) = step { self.scan_expr_for_stdlib(s); }
            }
            Expr::ListLiteral { elements, .. } | Expr::SetLiteral { elements, .. } |
            Expr::TupleLiteral { elements, .. } => {
                for e in elements {
                    self.scan_expr_for_stdlib(e);
                }
            }
            Expr::DictLiteral { entries, .. } => {
                for (k, v) in entries {
                    self.scan_expr_for_stdlib(k);
                    self.scan_expr_for_stdlib(v);
                }
            }
            Expr::Comprehension { expr, bindings, condition, .. } => {
                self.scan_expr_for_stdlib(expr);
                for b in bindings {
                    self.scan_expr_for_stdlib(&b.iterable);
                }
                if let Some(c) = condition {
                    self.scan_expr_for_stdlib(c);
                }
            }
            Expr::IfExpr { condition, then_expr, else_expr, .. } => {
                self.scan_expr_for_stdlib(condition);
                self.scan_expr_for_stdlib(then_expr);
                self.scan_expr_for_stdlib(else_expr);
            }
            Expr::SafeNav { target, .. } => self.scan_expr_for_stdlib(target),
            Expr::NullCoalesce { left, right, .. } => {
                self.scan_expr_for_stdlib(left);
                self.scan_expr_for_stdlib(right);
            }
            Expr::TypeCast { expr, .. } | Expr::Await { expr, .. } => {
                self.scan_expr_for_stdlib(expr);
            }
            Expr::Yield { value: Some(v), .. } => self.scan_expr_for_stdlib(v),
            _ => {}
        }
    }

    /// Collect transtime directives — executed at Vox transpilation time
    fn collect_transtime(&mut self, module: &Module) {
        for stmt in &module.statements {
            if let Stmt::TranstimeBlock { body, .. } = stmt {
                for s in body {
                    self.exec_transtime_stmt(s);
                }
            }
        }
    }

    /// Execute a single transtime statement
    fn exec_transtime_stmt(&mut self, stmt: &Stmt) {
        match stmt {
            Stmt::ExprStmt { expr, .. } => {
                self.exec_transtime_expr(expr);
            }
            _ => {}
        }
    }

    /// Execute a transtime expression — interpret special calls
    fn exec_transtime_expr(&mut self, expr: &Expr) {
        match expr {
            Expr::MethodCall { receiver, method, args, .. } => {
                // Handle toml.dependency("serde", "1.0")
                if let Expr::Ident { name, .. } = receiver.as_ref() {
                    if name == "toml" {
                        self.exec_toml_directive(method, args);
                        return;
                    }
                    if name == "config" {
                        self.exec_config_directive(method, args);
                        return;
                    }
                    if name == "file" {
                        self.exec_file_directive(method, args);
                        return;
                    }
                }
            }
            Expr::Call { func, args, .. } => {
                // Handle dependency("serde", "1.0") or add_dep(...)
                if let Expr::Ident { name, .. } = func.as_ref() {
                    if name == "dependency" || name == "add_dep" {
                        self.exec_toml_directive("dependency", args);
                        return;
                    }
                    if name == "feature" || name == "add_feature" {
                        self.exec_toml_directive("feature", args);
                        return;
                    }
                    if name == "file" || name == "write_file" {
                        self.exec_file_directive("write", args);
                        return;
                    }
                    if name == "config" {
                        self.exec_config_directive("set", args);
                        return;
                    }
                }
            }
            _ => {}
        }
    }

    /// Execute toml.* directives
    fn exec_toml_directive(&mut self, method: &str, args: &[Expr]) {
        match method {
            "dependency" | "add_dep" => {
                let crate_name = self.extract_string_arg(args, 0);
                let version = self.extract_string_arg(args, 1);
                if let (Some(name), Some(ver)) = (crate_name, version) {
                    self.transtime.dependencies.push((name, ver));
                }
            }
            "feature" | "add_feature" => {
                let crate_name = self.extract_string_arg(args, 0);
                let features = self.extract_string_list_arg(args, 1);
                if let (Some(name), Some(feats)) = (crate_name, features) {
                    self.transtime.features.push((name, feats));
                }
            }
            _ => {}
        }
    }

    /// Execute config.* directives
    fn exec_config_directive(&mut self, method: &str, args: &[Expr]) {
        match method {
            "set" => {
                let key = self.extract_string_arg(args, 0);
                let value = self.extract_string_arg(args, 1);
                if let (Some(k), Some(v)) = (key, value) {
                    self.transtime.config.push((k, v));
                }
            }
            _ => {}
        }
    }

    /// Execute file.* directives — generate extra source files
    fn exec_file_directive(&mut self, method: &str, args: &[Expr]) {
        match method {
            "write" | "create" => {
                let filename = self.extract_string_arg(args, 0);
                let content = self.extract_string_arg(args, 1);
                if let (Some(fname), Some(cont)) = (filename, content) {
                    self.transtime.extra_files.push((fname, cont));
                }
            }
            _ => {}
        }
    }

    /// Extract a string argument from an expression
    fn extract_string_arg(&self, args: &[Expr], index: usize) -> Option<String> {
        args.get(index).and_then(|arg| {
            if let Expr::Literal { value: LiteralValue::String(s), .. } = arg {
                Some(s.clone())
            } else {
                None
            }
        })
    }

    /// Extract a list of strings from an expression
    fn extract_string_list_arg(&self, args: &[Expr], index: usize) -> Option<Vec<String>> {
        args.get(index).and_then(|arg| {
            if let Expr::ListLiteral { elements, .. } = arg {
                Some(elements.iter().filter_map(|e| {
                    if let Expr::Literal { value: LiteralValue::String(s), .. } = e {
                        Some(s.clone())
                    } else {
                        None
                    }
                }).collect())
            } else {
                None
            }
        })
    }

    /// Set the current Vox source position for source map tracking
    fn set_vox_position(&mut self, span: &Span) {
        self.current_vox_file = span.file.clone();
        self.current_vox_line = span.line;
    }

    fn gen_stmt(&mut self, stmt: &Stmt) {
        // Extract span for source map tracking
        let span = match stmt {
            Stmt::VarDecl { span, .. } => span.clone(),
            Stmt::FnDef { span, .. } => span.clone(),
            Stmt::StructDef { span, .. } => span.clone(),
            Stmt::EnumDef { span, .. } => span.clone(),
            Stmt::ClassDef { span, .. } => span.clone(),
            Stmt::TraitDef { span, .. } => span.clone(),
            Stmt::ImplBlock { span, .. } => span.clone(),
            Stmt::MatchStmt { span, .. } => span.clone(),
            Stmt::ReturnStmt { span, .. } => span.clone(),
            Stmt::ExprStmt { span, .. } => span.clone(),
            Stmt::IfStmt { span, .. } => span.clone(),
            Stmt::ConstDecl { span, .. } => span.clone(),
            Stmt::LazyDecl { span, .. } => span.clone(),
            Stmt::TestStmt { span, .. } => span.clone(),
            Stmt::SuiteStmt { span, .. } => span.clone(),
            Stmt::ImportStmt { span, .. } => span.clone(),
            Stmt::FromImport { span, .. } => span.clone(),
            Stmt::IgnoreStmt { span, .. } => span.clone(),
            Stmt::ExcludeStmt { span, .. } => span.clone(),
            _ => Span::unknown(),
        };
        self.set_vox_position(&span);

        match stmt {
            Stmt::VarDecl { mutable, name, type_annotation, value, .. } => {
                let keyword = "let mut";
                let type_str = type_annotation
                    .as_ref()
                    .map(|t| format!(": {}", self.gen_type(t)))
                    .unwrap_or_default();
                let inferred_vox_type = if let Some(ty) = type_annotation {
                    ty.name()
                } else {
                    self.infer_expr_type(value).unwrap_or_else(|| "int".to_string())
                };
                self.var_types.insert(name.clone(), inferred_vox_type);
                self.emit_line(&format!(
                    "{} {}{} = {};",
                    keyword,
                    name,
                    type_str,
                    self.gen_expr(value)
                ));
            }
            Stmt::ConstDecl { name, type_annotation, value, .. } => {
                match type_annotation {
                    Some(ty) => {
                        let type_str = self.gen_type(ty);
                        self.emit_line(&format!("const {}: {} = {};", name, type_str, self.gen_expr(value)));
                    }
                    None => {
                        // Infer type from value
                        let inferred_type = match value.as_ref() {
                            Expr::Literal { value: LiteralValue::Int(_), .. } => "i64",
                            Expr::Literal { value: LiteralValue::Float(_), .. } => "f64",
                            Expr::Literal { value: LiteralValue::String(_), .. } => "&str",
                            Expr::Literal { value: LiteralValue::Bool(_), .. } => "bool",
                            _ => "i64",
                        };
                        self.emit_line(&format!("const {}: {} = {};", name, inferred_type, self.gen_expr(value)));
                    }
                }
            }
            Stmt::LazyDecl { name, type_annotation, value, .. } => {
                // lazy var x = expr → static X: OnceLock<Type> = OnceLock::new();
                // Access via X.get_or_init(|| expr)
                self.lazy_vars.insert(name.clone());
                let static_name = name.to_uppercase();
                let type_str = match type_annotation {
                    Some(ty) => self.gen_type(ty),
                    None => {
                        // Infer from value
                        match value.as_ref() {
                            Expr::Literal { value: LiteralValue::Int(_), .. } => "i64",
                            Expr::Literal { value: LiteralValue::Float(_), .. } => "f64",
                            Expr::Literal { value: LiteralValue::String(_), .. } => "String",
                            Expr::Literal { value: LiteralValue::Bool(_), .. } => "bool",
                            _ => "i64",
                        }.to_string()
                    }
                };
                self.emit_line(&format!("static {}: std::sync::LazyLock<{}> = std::sync::LazyLock::new(|| {{ {} }});", static_name, type_str, self.gen_expr(value)));
            }
            Stmt::FnDef { name, params, return_type, body, doc, .. } => {
                if let Some(d) = doc {
                    self.emit_line(&format!("#[doc = \"{}\"]", self.escape_string(d)));
                }
                let params_str: Vec<String> = params.iter().map(|p| self.gen_param(p)).collect();
                let ret_str = return_type
                    .as_ref()
                    .map(|t| format!(" -> {}", self.gen_type(t)))
                    .unwrap_or_default();
                self.emit_line(&format!("fn {}({}){} {{", name, params_str.join(", "), ret_str));
                self.indent_level += 1;
                if name == "main" {
                    self.emit_line("vox_install_panic_hook();");
                }
                for s in body {
                    self.gen_stmt(s);
                }
                self.indent_level -= 1;
                self.emit_line("}");
            }
            Stmt::ExprStmt { expr, .. } => {
                self.emit_line(&format!("{};", self.gen_expr(expr)));
            }
            Stmt::ReturnStmt { value, .. } => {
                match value {
                    Some(v) => self.emit_line(&format!("return {};", self.gen_expr(v))),
                    None => self.emit_line("return;"),
                }
            }
            Stmt::IfStmt { condition, then_body, elif_chain, else_body, .. } => {
                self.emit_line(&format!("if {} {{", self.gen_expr(condition)));
                self.indent_level += 1;
                for s in then_body {
                    self.gen_stmt(s);
                }
                self.indent_level -= 1;
                for (cond, body) in elif_chain {
                    self.emit_line(&format!("}} else if {} {{", self.gen_expr(cond)));
                    self.indent_level += 1;
                    for s in body {
                        self.gen_stmt(s);
                    }
                    self.indent_level -= 1;
                }
                if let Some(else_b) = else_body {
                    self.emit_line("} else {");
                    self.indent_level += 1;
                    for s in else_b {
                        self.gen_stmt(s);
                    }
                    self.indent_level -= 1;
                }
                self.emit_line("}");
            }
            Stmt::TestStmt { name, body, .. } => {
                self.emit_line("#[test]");
                self.emit_line(&format!("fn {}() {{", name));
                self.indent_level += 1;
                for s in body {
                    self.gen_stmt(s);
                }
                self.indent_level -= 1;
                self.emit_line("}");
            }
            Stmt::SuiteStmt { name, body, .. } => {
                self.emit_line("#[cfg(test)]");
                self.emit_line(&format!("mod {} {{", name));
                self.indent_level += 1;
                self.emit_line("use super::*;");
                for s in body {
                    self.gen_stmt(s);
                }
                self.indent_level -= 1;
                self.emit_line("}");
            }
            Stmt::DefineDecl { name, .. } => {
                self.emit_line(&format!("// define {} (type constraint — checked at compile time)", name));
            }
            Stmt::TemplateDecl { name, .. } => {
                self.emit_line(&format!("// template {} (expanded at compile time)", name));
            }
            Stmt::OperatorDecl { op_type, symbol, name, .. } => {
                self.emit_line(&format!("// operator {:?} {} {} (expanded at compile time)", op_type, symbol, name));
            }
            Stmt::DecoratedStmt { decorators, stmt, .. } => {
                for decorator in decorators {
                    self.emit_line(&format!("#[{}]", decorator));
                }
                self.gen_stmt(stmt);
            }
            Stmt::StructDef { name, generics, fields, doc, .. } => {
                if let Some(d) = doc {
                    self.emit_line(&format!("#[doc = \"{}\"]", self.escape_string(d)));
                }
                let generics_str = self.gen_generics_def(generics);
                self.emit_line(&format!("pub struct {}{} {{", name, generics_str));
                self.indent_level += 1;
                for field in fields {
                    let type_str = self.gen_field_type(name, &field.name, &field.type_annotation);
                    self.emit_line(&format!("pub {}: {},", field.name, type_str));
                }
                self.indent_level -= 1;
                self.emit_line("}");
            }
            Stmt::EnumDef { name, generics, variants, doc, .. } => {
                if let Some(d) = doc {
                    self.emit_line(&format!("#[doc = \"{}\"]", self.escape_string(d)));
                }
                let generics_str = self.gen_generics_def(generics);
                self.emit_line(&format!("pub enum {}{} {{", name, generics_str));
                self.indent_level += 1;
                for v in variants {
                    match &v.data {
                        Some(data_type) => {
                            let type_str = self.gen_type(data_type);
                            self.emit_line(&format!("{}({}),", v.name, type_str));
                        }
                        None => {
                            self.emit_line(&format!("{},", v.name));
                        }
                    }
                }
                self.indent_level -= 1;
                self.emit_line("}");
            }
            Stmt::ClassDef { name, parent, fields, methods, doc, .. } => {
                if let Some(d) = doc {
                    self.emit_line(&format!("#[doc = \"{}\"]", self.escape_string(d)));
                }
                if let Some(p) = parent {
                    self.emit_line(&format!("pub struct {} extends {} {{", name, p));
                } else {
                    self.emit_line(&format!("pub struct {} {{", name));
                }
                self.indent_level += 1;
                for field in fields {
                    let mut_str = if field.mutable { "pub " } else { "" };
                    let type_str = field.type_annotation.as_ref()
                        .map(|t| self.gen_type(t))
                        .unwrap_or_else(|| "i64".to_string());
                    if let Some(default) = &field.default {
                        let default_str = self.gen_expr(default);
                        self.emit_line(&format!("{}{}: {} = {},", mut_str, field.name, type_str, default_str));
                    } else {
                        self.emit_line(&format!("{}{}: {},", mut_str, field.name, type_str));
                    }
                }
                self.indent_level -= 1;
                self.emit_line("}");
                if !methods.is_empty() {
                    self.emit_line(&format!("impl {} {{", name));
                    self.indent_level += 1;
                    for method in methods {
                        self.gen_stmt(method);
                    }
                    self.indent_level -= 1;
                    self.emit_line("}");
                }
            }
            Stmt::TraitDef { name, methods, doc, .. } => {
                if let Some(d) = doc {
                    self.emit_line(&format!("#[doc = \"{}\"]", self.escape_string(d)));
                }
                self.emit_line(&format!("pub trait {} {{", name));
                self.indent_level += 1;
                for method in methods {
                    let return_str = method.return_type.as_ref()
                        .map(|t| format!(" -> {}", self.gen_type(t)))
                        .unwrap_or_default();
                    let params_str: Vec<String> = method.params.iter()
                        .map(|p| self.gen_param(p))
                        .collect();
                    if let Some(default_body) = &method.default_body {
                        self.emit_line(&format!("fn {}({}){}{{", method.name, params_str.join(", "), return_str));
                        self.indent_level += 1;
                        for s in default_body {
                            self.gen_stmt(s);
                        }
                        self.indent_level -= 1;
                        self.emit_line("}");
                    } else {
                        self.emit_line(&format!("fn {}({}){}; ", method.name, params_str.join(", "), return_str));
                    }
                }
                self.indent_level -= 1;
                self.emit_line("}");
            }
            Stmt::ImplBlock { trait_name, type_name, methods, .. } => {
                if let Some(trait_name) = trait_name {
                    self.emit_line(&format!("impl {} for {} {{", trait_name, type_name));
                } else {
                    self.emit_line(&format!("impl {} {{", type_name));
                }
                self.indent_level += 1;
                for method in methods {
                    self.gen_stmt(method);
                }
                self.indent_level -= 1;
                self.emit_line("}");
            }
            Stmt::ExtendDecl { target, for_type, methods, .. } => {
                self.emit_line(&format!("impl {} for {} {{", target, for_type));
                self.indent_level += 1;
                for method in methods {
                    self.gen_stmt(method);
                }
                self.indent_level -= 1;
                self.emit_line("}");
            }
            Stmt::MatchStmt { expr, arms, .. } => {
                self.emit_line(&format!("match {} {{", self.gen_expr(expr)));
                self.indent_level += 1;
                for arm in arms {
                    let pattern_str = self.gen_pattern(&arm.pattern);
                    let guard_str = arm.guard.as_ref()
                        .map(|g| format!(" if {}", self.gen_expr(g)))
                        .unwrap_or_default();
                    self.emit_line(&format!("{}{} => {{", pattern_str, guard_str));
                    self.indent_level += 1;
                    for s in &arm.body {
                        self.gen_stmt(s);
                    }
                    self.indent_level -= 1;
                    self.emit_line("}");
                }
                self.indent_level -= 1;
                self.emit_line("}");
            }
            Stmt::ImportStmt { module, items, alias, .. } => {
                // import foo::bar → use foo::bar;
                // import foo → mod foo; use foo::*;
                // import foo as f → mod foo; use foo as f;
                let module_path = module.join("::");
                if let Some(items) = items {
                    // import foo::{bar, baz} → use foo::{bar, baz};
                    let items_str = items.join(", ");
                    self.emit_line(&format!("use {}::{{{}}};", module_path, items_str));
                } else if let Some(alias) = alias {
                    // import foo as f → mod foo; use foo as f;
                    self.emit_line(&format!("mod {};", module_path));
                    self.emit_line(&format!("use {} as {};", module_path, alias));
                } else {
                    // import foo → mod foo; use foo::*;
                    self.emit_line(&format!("mod {};", module_path));
                    self.emit_line(&format!("use {}::*;", module_path));
                }
            }
            Stmt::FromImport { module, items, .. } => {
                // from foo import bar, baz → use foo::{bar, baz};
                let module_path = module.join("::");
                let items_str = items.join(", ");
                self.emit_line(&format!("use {}::{{{}}};", module_path, items_str));
            }
            Stmt::ComptimeBlock { body, .. } => {
                // comptime: generates Rust const code, evaluated by rustc
                self.emit_line("// comptime block — evaluated by rustc at compile time");
                self.indent_level += 1;
                self.emit_line("const _: () = {");
                self.indent_level += 1;
                for s in body {
                    self.gen_stmt(s);
                }
                self.indent_level -= 1;
                self.emit_line("};");
                self.indent_level -= 1;
            }
            Stmt::TranstimeBlock { .. } => {
                // transtime: already processed in collect_transtime, emit nothing
            }
            Stmt::IgnoreStmt { target, name, body, .. } => {
                // ignore test name: ... → emits #[test] #[ignore] fn name() { ... }
                if target == "test" {
                    self.emit_line("#[test]");
                    self.emit_line("#[ignore]");
                    self.emit_line(&format!("fn {}() {{", name));
                    self.indent_level += 1;
                    for s in body {
                        self.gen_stmt(s);
                    }
                    self.indent_level -= 1;
                    self.emit_line("}");
                } else {
                    // Generic ignore — emit as attribute comment
                    self.emit_line(&format!("// ignore {}", target));
                    for s in body {
                        self.gen_stmt(s);
                    }
                }
            }
            Stmt::ExcludeStmt { module, items, .. } => {
                // exclude module { item1, item2 }
                // Imports everything from module EXCEPT listed items.
                // Handled at import resolution time; emit as a comment for now.
                let module_path = module.join("::");
                let items_str = items.join(", ");
                self.emit_line(&format!(
                    "// exclude {} {{ {} }} — imports everything except these items",
                    module_path, items_str
                ));
            }
            _ => {
                self.emit_line(&format!("// TODO: codegen for {:?}", std::mem::discriminant(stmt)));
            }
        }
    }

    /// Try to infer the type of an expression for self-ref field detection
    fn infer_expr_type(&self, expr: &Expr) -> Option<String> {
        match expr {
            Expr::Ident { name, .. } => {
                if self.struct_types.contains(name) || self.enum_types.contains(name) {
                    Some(name.clone())
                } else {
                    self.var_types.get(name).cloned()
                }
            }
            Expr::Literal { value, .. } => match value {
                LiteralValue::Int(_) => Some("int".to_string()),
                LiteralValue::Float(_) => Some("float".to_string()),
                LiteralValue::String(_) => Some("str".to_string()),
                LiteralValue::Bool(_) => Some("bool".to_string()),
                LiteralValue::None => Some("void".to_string()),
            },
            Expr::ListLiteral { .. } => Some("list".to_string()),
            Expr::DictLiteral { .. } => Some("dict".to_string()),
            Expr::SetLiteral { .. } => Some("set".to_string()),
            Expr::TupleLiteral { .. } => Some("tuple".to_string()),
            Expr::BinaryOp { left, op, right, .. } => {
                let left_ty = self.infer_expr_type(left);
                let right_ty = self.infer_expr_type(right);
                match (left_ty, right_ty) {
                    (Some(l), Some(r)) if l == r => Some(l),
                    (Some(l), _) => Some(l),
                    (_, Some(r)) => Some(r),
                    _ => None,
                }
            }
            Expr::UnaryOp { operand, .. } => self.infer_expr_type(operand),
            _ => None,
        }
    }

    fn gen_expr(&self, expr: &Expr) -> String {
        match expr {
            Expr::Literal { value, .. } => self.gen_literal(value),
            Expr::Ident { name, .. } => {
                // Check if this is a lazy variable
                if self.lazy_vars.contains(name) {
                    let static_name = name.to_uppercase();
                    format!("*{}", static_name)
                } else {
                    name.clone()
                }
            }
            Expr::BinaryOp { left, op, right, .. } => {
                match op {
                    BinaryOperator::In => {
                        // `x in container` → `container.contains(&x)`
                        format!("({}).contains(&{})", self.gen_expr(right), self.gen_expr(left))
                    }
                    BinaryOperator::NotIn => {
                        // `x not in container` → `!(container).contains(&x)`
                        format!("!({}).contains(&{})", self.gen_expr(right), self.gen_expr(left))
                    }
                    _ => {
                        format!("{} {} {}", self.gen_expr(left), self.gen_binop(op), self.gen_expr(right))
                    }
                }
            }
            Expr::UnaryOp { op, operand, .. } => {
                format!("{}{}", self.gen_unop(op), self.gen_expr(operand))
            }
            Expr::Call { func, args, .. } => {
                let args_str = args.iter().map(|a| self.gen_expr(a)).collect::<Vec<_>>().join(", ");
                match func.as_ref() {
                    Expr::Ident { name, .. } if name == "print" => {
                        let format_parts: Vec<String> = args.iter().map(|_| "{:?}".to_string()).collect();
                        let format_str = format_parts.join(" ");
                        let args_str = args.iter().map(|a| self.gen_expr(a)).collect::<Vec<_>>().join(", ");
                        format!("print!(\"{}\", {})", format_str, args_str)
                    }
                    Expr::Ident { name, .. } if name == "println" => {
                        let format_parts: Vec<String> = args.iter().map(|_| "{:?}".to_string()).collect();
                        let format_str = format_parts.join(" ");
                        let args_str = args.iter().map(|a| self.gen_expr(a)).collect::<Vec<_>>().join(", ");
                        format!("println!(\"{}\", {})", format_str, args_str)
                    }
                    Expr::Ident { name, .. } if name == "len" => {
                        format!("{}.len()", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "type" => {
                        format!("std::any::type_name::<_>()")
                    }
                    Expr::Ident { name, .. } if name == "str" => {
                        format!("{}.to_string()", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "int" => {
                        format!("format!(\"{{}}\", {}).parse::<i64>().unwrap_or(0)", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "float" => {
                        format!("format!(\"{{}}\", {}).parse::<f64>().unwrap_or(0.0)", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "bool" => {
                        // Improve truthiness: handle bool, str, and collections
                        let arg = &args[0];
                        let arg_str = self.gen_expr(arg);
                        match self.infer_expr_type(arg).as_deref() {
                            Some("bool") => format!("({})", arg_str),
                            Some("str") => format!("!({}).is_empty()", arg_str),
                            Some("list") | Some("dict") | Some("set") => {
                                format!("!({}).is_empty()", arg_str)
                            }
                            _ => format!("({}) != 0", arg_str),
                        }
                    }
                    Expr::Ident { name, .. } if name == "Some" => {
                        format!("Some({})", args_str)
                    }
                    Expr::Ident { name, .. } if name == "None" => {
                        "None".to_string()
                    }
                    Expr::Ident { name, .. } if name == "Ok" => {
                        format!("Ok({})", args_str)
                    }
                    Expr::Ident { name, .. } if name == "Err" => {
                        format!("Err({})", args_str)
                    }
                    // === Math builtins ===
                    Expr::Ident { name, .. } if name == "abs" => {
                        format!("({}).abs()", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "round" => {
                        if args.len() >= 2 {
                            let x = self.gen_expr(&args[0]);
                            let d = self.gen_expr(&args[1]);
                            format!(
                                "((({}) * 10_f64.powi(({}) as i32)).round()) / 10_f64.powi(({}) as i32)",
                                x, d, d
                            )
                        } else {
                            format!("({}).round()", self.gen_expr(&args[0]))
                        }
                    }
                    Expr::Ident { name, .. } if name == "pow" => {
                        let base = self.gen_expr(&args[0]);
                        let exp = self.gen_expr(&args[1]);
                        match self.infer_expr_type(&args[0]).as_deref() {
                            Some("float") => format!("({}).powf(({}) as f64)", base, exp),
                            _ => format!("({}).pow(({}) as u32)", base, exp),
                        }
                    }
                    Expr::Ident { name, .. } if name == "divmod" => {
                        let a = self.gen_expr(&args[0]);
                        let b = self.gen_expr(&args[1]);
                        format!("((({}) / ({}), ({}) % ({})))", a, b, a, b)
                    }
                    Expr::Ident { name, .. } if name == "min" => {
                        if args.len() == 1 {
                            format!("({}).iter().min()", self.gen_expr(&args[0]))
                        } else if args.len() == 2 {
                            format!("std::cmp::min({}, {})", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                        } else {
                            let exprs: Vec<String> = args.iter().map(|a| self.gen_expr(a)).collect();
                            format!("[{}].iter().min()", exprs.join(", "))
                        }
                    }
                    Expr::Ident { name, .. } if name == "max" => {
                        if args.len() == 1 {
                            format!("({}).iter().max()", self.gen_expr(&args[0]))
                        } else if args.len() == 2 {
                            format!("std::cmp::max({}, {})", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                        } else {
                            let exprs: Vec<String> = args.iter().map(|a| self.gen_expr(a)).collect();
                            format!("[{}].iter().max()", exprs.join(", "))
                        }
                    }
                    Expr::Ident { name, .. } if name == "sum" => {
                        format!("({}).iter().sum::<i64>()", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "floor" => {
                        format!("({}).floor()", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "ceil" => {
                        format!("({}).ceil()", self.gen_expr(&args[0]))
                    }
                    // === Character builtins ===
                    Expr::Ident { name, .. } if name == "chr" => {
                        format!("char::from_u32(({}) as u32).unwrap_or('\\0')", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "ord" => {
                        // Vox has no char type — extract first char from a String
                        format!("((({}).chars().next().unwrap_or('\\0')) as u32) as i64", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "hex" => {
                        format!("format!(\"0x{{:x}}\", {})", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "oct" => {
                        format!("format!(\"0o{{:o}}\", {})", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "bin" => {
                        format!("format!(\"0b{{:b}}\", {})", self.gen_expr(&args[0]))
                    }
                    // === Collection builtins ===
                    Expr::Ident { name, .. } if name == "all" => {
                        format!("({}).iter().all(|x| *x != 0)", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "any" => {
                        format!("({}).iter().any(|x| *x != 0)", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "iter" => {
                        format!("({}).iter()", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "next" => {
                        format!("({}).next()", self.gen_expr(&args[0]))
                    }
                    // === I/O builtins ===
                    Expr::Ident { name, .. } if name == "input" => {
                        if args.is_empty() {
                            "{ let mut __s = String::new(); io::stdout().flush().unwrap(); io::stdin().read_line(&mut __s).unwrap(); __s.trim().to_string() }".to_string()
                        } else {
                            format!(
                                "{{ print!(\"{{}}\", {}); io::stdout().flush().unwrap(); let mut __s = String::new(); io::stdin().read_line(&mut __s).unwrap(); __s.trim().to_string() }}",
                                self.gen_expr(&args[0])
                            )
                        }
                    }
                    Expr::Ident { name, .. } if name == "open" => {
                        if args.len() >= 2 {
                            let path = self.gen_expr(&args[0]);
                            let mode = self.gen_expr(&args[1]);
                            format!(
                                "{{ let __p = {}; let __m = {}; let __f = if __m.contains('w') {{ std::fs::OpenOptions::new().write(true).create(true).truncate(true).open(&__p) }} else if __m.contains('a') {{ std::fs::OpenOptions::new().append(true).create(true).open(&__p) }} else {{ std::fs::File::open(&__p) }}; __f.unwrap() }}",
                                path, mode
                            )
                        } else {
                            format!("std::fs::File::open({}).unwrap()", self.gen_expr(&args[0]))
                        }
                    }
                    // === Format ===
                    Expr::Ident { name, .. } if name == "format" => {
                        let placeholders: Vec<String> = args.iter().map(|_| "{}".to_string()).collect();
                        let exprs: Vec<String> = args.iter().map(|a| self.gen_expr(a)).collect();
                        format!("format!(\"{}\", {})", placeholders.join(" "), exprs.join(", "))
                    }
                    // === Functional programming builtins ===
                    Expr::Ident { name, .. } if name == "range" => {
                        match args.len() {
                            1 => format!("(0..{}).collect::<Vec<_>>()", self.gen_expr(&args[0])),
                            2 => format!("({}..{}).collect::<Vec<_>>()", self.gen_expr(&args[0]), self.gen_expr(&args[1])),
                            3 => format!("({}..{}).step_by({} as usize).collect::<Vec<_>>()", self.gen_expr(&args[0]), self.gen_expr(&args[1]), self.gen_expr(&args[2])),
                            _ => "vec![]".to_string(),
                        }
                    }
                    Expr::Ident { name, .. } if name == "map" => {
                        let func = self.gen_expr(&args[0]);
                        let iterable = self.gen_expr(&args[1]);
                        format!("{}.iter().cloned().map(|x| ({})(x)).collect::<Vec<_>>()", iterable, func)
                    }
                    Expr::Ident { name, .. } if name == "filter" => {
                        let func = self.gen_expr(&args[0]);
                        let iterable = self.gen_expr(&args[1]);
                        format!("{}.iter().cloned().filter(|&x| ({})(x)).collect::<Vec<_>>()", iterable, func)
                    }
                    Expr::Ident { name, .. } if name == "zip" => {
                        let a = self.gen_expr(&args[0]);
                        let b = self.gen_expr(&args[1]);
                        format!("{}.iter().zip({}.iter()).map(|(a, b)| (a.clone(), b.clone())).collect::<Vec<_>>()", a, b)
                    }
                    Expr::Ident { name, .. } if name == "enumerate" => {
                        let iterable = self.gen_expr(&args[0]);
                        format!("{}.iter().enumerate().map(|(i, x)| (i as i64, x.clone())).collect::<Vec<_>>()", iterable)
                    }
                    Expr::Ident { name, .. } if name == "reversed" => {
                        let iterable = self.gen_expr(&args[0]);
                        format!("{{ let mut v = {}.clone(); v.reverse(); v }}", iterable)
                    }
                    Expr::Ident { name, .. } if name == "sorted" => {
                        let iterable = self.gen_expr(&args[0]);
                        let reverse = args.iter().skip(1).any(|arg| {
                            matches!(arg, Expr::Literal { value: LiteralValue::Bool(true), .. })
                        });
                        if reverse {
                            format!("{{ let mut v = {}.clone(); v.sort(); v.reverse(); v }}", iterable)
                        } else {
                            format!("{{ let mut v = {}.clone(); v.sort(); v }}", iterable)
                        }
                    }
                    Expr::Ident { name, .. } if name == "slice" => {
                        let args_str = args.iter().map(|a| self.gen_expr(a)).collect::<Vec<_>>().join(", ");
                        format!("({})", args_str)
                    }
                    // === Introspection builtins ===
                    Expr::Ident { name, .. } if name == "dir" => {
                        format!("vox_dir(&{})", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "help" => {
                        format!("{{ println!(\"{{}}\", vox_help(&{})); }}", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "repr" => {
                        format!("format!(\"{{:?}}\", {})", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "id" => {
                        format!("vox_id(&{})", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "hash" => {
                        format!("vox_hash(&{})", self.gen_expr(&args[0]))
                    }
                    Expr::Ident { name, .. } if name == "callable" => {
                        "false".to_string()
                    }
                    Expr::Ident { name, .. } if name == "isinstance" => {
                        let val = self.gen_expr(&args[0]);
                        let type_name = match &args[1] {
                            Expr::Ident { name, .. } => name.clone(),
                            _ => self.gen_expr(&args[1]),
                        };
                        format!("vox_isinstance(&{}, \"{}\")", val, type_name)
                    }
                    Expr::Ident { name, .. } if name == "issubclass" => {
                        "false".to_string()
                    }
                    Expr::Ident { name, .. } if name == "hasattr" => {
                        "false".to_string()
                    }
                    Expr::Ident { name, .. } if name == "getattr" => {
                        "panic!(\"getattr not supported\")".to_string()
                    }
                    Expr::Ident { name, .. } if name == "setattr" => {
                        "panic!(\"setattr not supported\")".to_string()
                    }
                    Expr::Ident { name, .. } if name == "vars" => {
                        "std::collections::HashMap::<String, String>::new()".to_string()
                    }
                    Expr::Ident { name, .. } if name == "globals" => {
                        "std::collections::HashMap::<String, String>::new()".to_string()
                    }
                    Expr::Ident { name, .. } if name == "locals" => {
                        "std::collections::HashMap::<String, String>::new()".to_string()
                    }
                    Expr::Ident { name, .. } if self.struct_types.contains(name) => {
                        if let Some(fields) = self.struct_fields.get(name) {
                            let init: Vec<String> = fields.iter().zip(args.iter())
                                .map(|(f, a)| format!("{}: {}", f, self.gen_expr(a)))
                                .collect();
                            format!("{} {{ {} }}", name, init.join(", "))
                        } else {
                            format!("{}({})", name, args_str)
                        }
                    }
                    _ => format!("{}({})", self.gen_expr(func), args_str),
                }
            }
            Expr::MethodCall { receiver, method, args, .. } => {
                // Handle inspect.xxx() and reflect.xxx() as compile-time expansion
                if let Expr::Ident { name, .. } = receiver.as_ref() {
                    if name == "inspect" {
                        return self.gen_inspect_call(method, args);
                    }
                    if name == "reflect" {
                        return self.gen_reflect_call(method, args);
                    }
                    // Standard library modules: utils, logging, abc, ctypes
                    if name == "utils" {
                        return self.gen_utils_call(method, args);
                    }
                    if name == "logging" {
                        return self.gen_logging_call(method, args);
                    }
                    if name == "abc" {
                        return self.gen_abc_call(method, args);
                    }
                    if name == "ctypes" {
                        return self.gen_ctypes_call(method, args);
                    }
                    // Standard library modules: time, datetime, copy, weakref
                    if name == "time" {
                        return self.gen_time_call(method, args);
                    }
                    if name == "datetime" {
                        return self.gen_datetime_call(method, args);
                    }
                    if name == "copy" {
                        return self.gen_copy_call(method, args);
                    }
                    if name == "weakref" {
                        return self.gen_weakref_call(method, args);
                    }
                    // Standard library modules: string, re, funcs
                    if name == "string" {
                        return self.gen_stdlib_string_call(method, args);
                    }
                    if name == "re" {
                        return self.gen_stdlib_re_call(method, args);
                    }
                    if name == "funcs" {
                        return self.gen_stdlib_funcs_call(method, args);
                    }
                    // Standard library modules: gc, collection, itors
                    if name == "gc" || name == "collection" || name == "itors" {
                        return self.gen_stdlib_call(name, method, args);
                    }
                    // Standard library modules: sys, os, fs
                    if self.is_std_module(name) {
                        if let Some(code) = self.gen_module_call(name, method, args) {
                            return code;
                        }
                    }
                }
                // Handle nested submodule calls: os.path.exists(path)
                if let Expr::Attribute { target, name: sub_name, .. } = receiver.as_ref() {
                    if let Expr::Ident { name: mod_name, .. } = target.as_ref() {
                        if self.is_std_module(mod_name) && self.is_std_submodule(mod_name, sub_name) {
                            let full_name = format!("{}.{}", mod_name, sub_name);
                            if let Some(code) = self.gen_module_call(&full_name, method, args) {
                                return code;
                            }
                        }
                    }
                }
                let args_str = args.iter().map(|a| self.gen_expr(a)).collect::<Vec<_>>().join(", ");
                format!("{}.{}({})", self.gen_expr(receiver), method, args_str)
            }
            Expr::Attribute { target, name, .. } => {
                // Handle ctypes type constants: ctypes.c_int, ctypes.c_long, etc.
                if let Expr::Ident { name: mod_name, .. } = target.as_ref() {
                    if mod_name == "ctypes" {
                        if let Some(rust_type) = self.ctypes_type_to_rust(name) {
                            // Return type name as string — used by ctypes.sizeof() etc.
                            return format!("\"{}\".to_string()", rust_type);
                        }
                    }
                    // Handle logging level constants: logging.DEBUG, logging.INFO, etc.
                    if mod_name == "logging" {
                        if let Some(level) = self.logging_level_value(name) {
                            return level.to_string();
                        }
                    }
                    // Handle string module constants: string.digits, string.ascii_letters, etc.
                    if mod_name == "string" {
                        if let Some(lit) = self.string_constant(name) {
                            return lit;
                        }
                    }
                    // Handle std module properties: sys.platform, os.sep, etc.
                    if self.is_std_module(mod_name) {
                        if let Some(code) = self.gen_module_attr(mod_name, name) {
                            return code;
                        }
                    }
                }
                // Check if this is a self-referential field access
                let target_type = self.infer_expr_type(target);
                if let Some(ty) = &target_type {
                    if let Some(meta) = self.type_metadata.get(ty) {
                        if meta.self_ref_fields.contains(name) {
                            // Auto-deref: node.next → node.next.as_ref().unwrap()
                            return format!("{{ let __v = {}.{}; __v.as_ref().unwrap().clone() }}", self.gen_expr(target), name);
                        }
                    }
                }
                format!("{}.{}", self.gen_expr(target), name)
            }
            Expr::Lambda { params, body, .. } => {
                let params_str = params.join(", ");
                format!("|{}| {}", params_str, self.gen_expr(body))
            }
            Expr::ListLiteral { elements, .. } => {
                let elems = elements.iter().map(|e| self.gen_expr(e)).collect::<Vec<_>>().join(", ");
                if elements.is_empty() {
                    // Empty vec needs a type annotation so Rust can infer the element type
                    "Vec::<i64>::new()".to_string()
                } else {
                    format!("vec![{}]", elems)
                }
            }
            Expr::DictLiteral { entries, .. } => {
                if entries.is_empty() {
                    "HashMap::<String, String>::new()".to_string()
                } else {
                    let entries_str = entries.iter().map(|(k, v)| {
                        format!("({}, {})", self.gen_expr(k), self.gen_expr(v))
                    }).collect::<Vec<_>>().join(", ");
                    format!("HashMap::from([{}])", entries_str)
                }
            }
            Expr::SetLiteral { elements, .. } => {
                let elems = elements.iter().map(|e| self.gen_expr(e)).collect::<Vec<_>>().join(", ");
                if elements.is_empty() {
                    "HashSet::<i64>::new()".to_string()
                } else {
                    format!("HashSet::from([{}])", elems)
                }
            }
            Expr::TupleLiteral { elements, .. } => {
                let elems = elements.iter().map(|e| self.gen_expr(e)).collect::<Vec<_>>().join(", ");
                format!("({})", elems)
            }
            _ => format!("/* TODO: expr */"),
        }
    }

    /// Check if an expression will generate a Vec<String> (from reflect)
    fn is_vec_expr(&self, expr: Option<&Expr>) -> bool {
        match expr {
            Some(Expr::MethodCall { receiver, method, .. }) => {
                if let Expr::Ident { name, .. } = receiver.as_ref() {
                    if name == "reflect" {
                        return matches!(method.as_str(), "fields" | "variants" | "methods" | "field_types");
                    }
                }
                false
            }
            _ => false,
        }
    }

    fn gen_inspect_or_reflect(&self, target: &Expr, method: &str, args: &[Expr]) -> String {
        match target {
            Expr::Ident { name, .. } if name == "inspect" => {
                self.gen_inspect_call(method, args)
            }
            Expr::Ident { name, .. } if name == "reflect" => {
                self.gen_reflect_call(method, args)
            }
            _ => format!("{}.{}({})", self.gen_expr(target), method, 
                args.iter().map(|a| self.gen_expr(a)).collect::<Vec<_>>().join(", ")),
        }
    }

    fn gen_inspect_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "source" => {
                if let Some(Expr::Ident { name, .. }) = args.first() {
                    if let Some(meta) = self.fn_metadata.get(name) {
                        let source = self.extract_source(&meta.span);
                        return format!("\"{}\".to_string()", self.escape_string(&source));
                    }
                }
                "\"/* unknown function */\".to_string()".to_string()
            }
            "signature" => {
                if let Some(Expr::Ident { name, .. }) = args.first() {
                    if let Some(meta) = self.fn_metadata.get(name) {
                        let sig = self.format_signature(meta);
                        return format!("\"{}\".to_string()", self.escape_string(&sig));
                    }
                }
                "\"/* unknown function */\".to_string()".to_string()
            }
            "getfile" => {
                if let Some(Expr::Ident { name, .. }) = args.first() {
                    if let Some(meta) = self.fn_metadata.get(name) {
                        return format!("\"{}\".to_string()", self.escape_string(&meta.span.file));
                    }
                }
                "\"\".to_string()".to_string()
            }
            "getsourcelines" => {
                if let Some(Expr::Ident { name, .. }) = args.first() {
                    if let Some(meta) = self.fn_metadata.get(name) {
                        let source = self.extract_source(&meta.span);
                        let lines: Vec<String> = source.lines()
                            .map(|l| format!("\"{}\".to_string()", self.escape_string(l)))
                            .collect();
                        return format!("vec![{}]", lines.join(", "));
                    }
                }
                "vec![]".to_string()
            }
            "lineno" => {
                if let Some(Expr::Ident { name, .. }) = args.first() {
                    if let Some(meta) = self.fn_metadata.get(name) {
                        return meta.span.line.to_string();
                    }
                }
                "0".to_string()
            }
            "doc" => {
                // inspect.doc("TypeName") — look up doc string by name at runtime
                if let Some(Expr::Literal { value: LiteralValue::String(s), .. }) = args.first() {
                    return format!("vox_doc_lookup(\"{}\")", self.escape_string(s));
                }
                "\"\".to_string()".to_string()
            }
            _ => format!("inspect.{}({})", method,
                args.iter().map(|a| self.gen_expr(a)).collect::<Vec<_>>().join(", ")),
        }
    }

    fn gen_reflect_call(&self, method: &str, args: &[Expr]) -> String {
        // Extract type name from first argument
        let type_name = match args.first() {
            Some(Expr::Ident { name, .. }) if self.type_metadata.contains_key(name) => name.clone(),
            _ => {
                // Fallback: emit as static string for unknown types
                return match method {
                    "type_name" => "\"<unknown>\".to_string()".to_string(),
                    "fields" | "methods" | "variants" | "field_types" => "vec![]".to_string(),
                    "is_struct" | "is_enum" | "is_class" | "is_trait" | "has_trait" => "false".to_string(),
                    "doc" => "\"\".to_string()".to_string(),
                    _ => format!("/* reflect.{}: unknown */", method),
                };
            }
        };

        match method {
            "type_name" => {
                format!("<{} as VoxReflect>::vox_type_name().to_string()", type_name)
            }
            "fields" => {
                format!("<{} as VoxReflect>::vox_fields().to_vec().into_iter().map(|s| s.to_string()).collect::<Vec<_>>()", type_name)
            }
            "field_types" => {
                format!("<{} as VoxReflect>::vox_field_types().to_vec().into_iter().map(|(n, t)| (n.to_string(), t.to_string())).collect::<Vec<_>>()", type_name)
            }
            "methods" => {
                format!("<{} as VoxReflect>::vox_methods().to_vec().into_iter().map(|s| s.to_string()).collect::<Vec<_>>()", type_name)
            }
            "variants" => {
                format!("<{} as VoxReflect>::vox_variants().to_vec().into_iter().map(|s| s.to_string()).collect::<Vec<_>>()", type_name)
            }
            "is_struct" => format!("<{} as VoxReflect>::vox_is_struct()", type_name),
            "is_enum" => format!("<{} as VoxReflect>::vox_is_enum()", type_name),
            "is_class" => format!("<{} as VoxReflect>::vox_is_class()", type_name),
            "is_trait" => format!("<{} as VoxReflect>::vox_is_trait()", type_name),
            "has_trait" => {
                // Two args: type name and trait name — kept as compile-time expansion
                // because Rust's trait system is not easily checkable at runtime.
                if args.len() >= 2 {
                    if let Some(Expr::Ident { name: trait_name, .. }) = args.get(1) {
                        if let Some(traits) = self.impl_traits.get(&type_name) {
                            return traits.contains(trait_name).to_string();
                        }
                    }
                }
                "false".to_string()
            }
            "doc" => format!("vox_doc_lookup(\"{}\")", self.escape_string(&type_name)),
            _ => format!("/* reflect.{}: not implemented */", method),
        }
    }

    // ===== Standard library: utils module =====

    /// Generate code for utils.xxx() calls
    fn gen_utils_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "is_none" => {
                if let Some(arg) = args.first() {
                    format!("({}).is_none()", self.gen_expr(arg))
                } else {
                    "/* utils.is_none: missing arg */".to_string()
                }
            }
            "is_some" => {
                if let Some(arg) = args.first() {
                    format!("({}).is_some()", self.gen_expr(arg))
                } else {
                    "/* utils.is_some: missing arg */".to_string()
                }
            }
            "unwrap" => {
                match args.len() {
                    1 => format!("({}).unwrap()", self.gen_expr(&args[0])),
                    _ => format!("({}).unwrap_or({})", self.gen_expr(&args[0]), self.gen_expr(&args[1])),
                }
            }
            "expect" => {
                if args.len() >= 2 {
                    format!("({}).expect(({}).as_str())", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* utils.expect: needs (x, msg) */".to_string()
                }
            }
            "try_parse" => {
                // utils.try_parse(s, type) → s.parse::<T>()
                if let Some(arg) = args.first() {
                    format!("({}).parse::<i64>().ok()", self.gen_expr(arg))
                } else {
                    "/* utils.try_parse: missing arg */".to_string()
                }
            }
            "to_string" => {
                if let Some(arg) = args.first() {
                    format!("({}).to_string()", self.gen_expr(arg))
                } else {
                    "/* utils.to_string: missing arg */".to_string()
                }
            }
            "debug_string" => {
                if let Some(arg) = args.first() {
                    format!("format!(\"{{:?}}\", {})", self.gen_expr(arg))
                } else {
                    "/* utils.debug_string: missing arg */".to_string()
                }
            }
            "type_id" => {
                if let Some(arg) = args.first() {
                    format!("std::any::Any::type_id(&{})", self.gen_expr(arg))
                } else {
                    "/* utils.type_id: missing arg */".to_string()
                }
            }
            "type_name" => {
                if let Some(arg) = args.first() {
                    format!("std::any::type_name_of_val(&{})", self.gen_expr(arg))
                } else {
                    "/* utils.type_name: missing arg */".to_string()
                }
            }
            "discard" => {
                if let Some(arg) = args.first() {
                    format!("{{ let _ = {}; }}", self.gen_expr(arg))
                } else {
                    "/* utils.discard: missing arg */".to_string()
                }
            }
            "identity" => {
                if let Some(arg) = args.first() {
                    self.gen_expr(arg)
                } else {
                    "/* utils.identity: missing arg */".to_string()
                }
            }
            "pipe" => {
                // utils.pipe(x, f) → f(x)
                if args.len() >= 2 {
                    format!("({})({})", self.gen_expr(&args[1]), self.gen_expr(&args[0]))
                } else {
                    "/* utils.pipe: needs (x, f) */".to_string()
                }
            }
            "compose" => {
                // utils.compose(f, g) → move |x| f(g(x))
                if args.len() >= 2 {
                    format!("move |x| ({})(({})(x))", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* utils.compose: needs (f, g) */".to_string()
                }
            }
            "chain" => {
                // utils.chain(funcs, x) → apply functions in sequence
                if args.len() >= 2 {
                    format!("{{ let __x = {}; ({})(__x) }}", self.gen_expr(&args[1]), self.gen_expr(&args[0]))
                } else {
                    "/* utils.chain: needs (funcs, x) */".to_string()
                }
            }
            "memoize" => {
                // utils.memoize(func) → simplified: wrap with HashMap cache (best-effort)
                if let Some(arg) = args.first() {
                    format!("{{ static __CACHE: std::sync::Mutex<std::collections::HashMap<String, String>> = std::sync::Mutex::new(std::collections::HashMap::new()); let _ = &__CACHE; {} }}", self.gen_expr(arg))
                } else {
                    "/* utils.memoize: missing arg */".to_string()
                }
            }
            "retry" => {
                // utils.retry(func, times) → loop with attempts
                if args.len() >= 2 {
                    format!("{{ let __times = {}; let mut __ok = false; for _ in 0..__times {{ if {{ let __r = ({}); __ok = true; __r }} {{ break; }} }} }}",
                        self.gen_expr(&args[1]), self.gen_expr(&args[0]))
                } else {
                    "/* utils.retry: needs (func, times) */".to_string()
                }
            }
            "debounce" | "throttle" | "timeout" => {
                // Simplified: just call the function (no real async timing in sync codegen)
                if let Some(arg) = args.first() {
                    format!("({})()", self.gen_expr(arg))
                } else {
                    format!("/* utils.{}: missing arg */", method)
                }
            }
            _ => format!("/* utils.{}: not implemented */", method),
        }
    }

    // ===== Standard library: logging module =====

    /// Map logging level name to numeric value (Python-style)
    fn logging_level_value(&self, name: &str) -> Option<i64> {
        match name {
            "DEBUG" => Some(10),
            "INFO" => Some(20),
            "WARNING" | "WARN" => Some(30),
            "ERROR" => Some(40),
            "CRITICAL" | "FATAL" => Some(50),
            "NOTSET" => Some(0),
            _ => None,
        }
    }

    /// Generate code for logging.xxx() calls
    fn gen_logging_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "debug" => {
                if let Some(arg) = args.first() {
                    format!("eprintln!(\"[DEBUG] {{}}\", {})", self.gen_expr(arg))
                } else {
                    "eprintln!(\"[DEBUG]\")".to_string()
                }
            }
            "info" => {
                if let Some(arg) = args.first() {
                    format!("eprintln!(\"[INFO] {{}}\", {})", self.gen_expr(arg))
                } else {
                    "eprintln!(\"[INFO]\")".to_string()
                }
            }
            "warning" | "warn" => {
                if let Some(arg) = args.first() {
                    format!("eprintln!(\"[WARNING] {{}}\", {})", self.gen_expr(arg))
                } else {
                    "eprintln!(\"[WARNING]\")".to_string()
                }
            }
            "error" => {
                if let Some(arg) = args.first() {
                    format!("eprintln!(\"[ERROR] {{}}\", {})", self.gen_expr(arg))
                } else {
                    "eprintln!(\"[ERROR]\")".to_string()
                }
            }
            "critical" | "fatal" => {
                if let Some(arg) = args.first() {
                    format!("eprintln!(\"[CRITICAL] {{}}\", {})", self.gen_expr(arg))
                } else {
                    "eprintln!(\"[CRITICAL]\")".to_string()
                }
            }
            "log" => {
                // logging.log(level, msg) → eprintln!("[{level}] {msg}")
                if args.len() >= 2 {
                    format!("eprintln!(\"[{{}}] {{}}\", {}, {})", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* logging.log: needs (level, msg) */".to_string()
                }
            }
            "basicConfig" => {
                // Simplified: emit a no-op comment (config stored statically is not supported in sync codegen)
                "// logging.basicConfig: configured (simplified)".to_string()
            }
            "getLogger" => {
                // Return a logger struct name as string
                if let Some(arg) = args.first() {
                    format!("VoxLogger::new({})", self.gen_expr(arg))
                } else {
                    "VoxLogger::new(\"root\")".to_string()
                }
            }
            "StreamHandler" => {
                "VoxStreamHandler".to_string()
            }
            "FileHandler" => {
                if let Some(arg) = args.first() {
                    format!("VoxFileHandler::new({})", self.gen_expr(arg))
                } else {
                    "/* logging.FileHandler: needs filename */".to_string()
                }
            }
            "Formatter" => {
                if let Some(arg) = args.first() {
                    format!("VoxFormatter::new({})", self.gen_expr(arg))
                } else {
                    "VoxFormatter::default()".to_string()
                }
            }
            "addLevelName" => {
                "// logging.addLevelName: level name registered (simplified)".to_string()
            }
            "getLevelName" => {
                if let Some(arg) = args.first() {
                    format!("match {} {{ 10 => \"DEBUG\", 20 => \"INFO\", 30 => \"WARNING\", 40 => \"ERROR\", 50 => \"CRITICAL\", _ => \"NOTSET\" }}.to_string()",
                        self.gen_expr(arg))
                } else {
                    "\"NOTSET\".to_string()".to_string()
                }
            }
            "disable" => {
                "// logging.disable: logging disabled below level (simplified)".to_string()
            }
            _ => format!("/* logging.{}: not implemented */", method),
        }
    }

    // ===== Standard library: abc module =====

    /// Generate code for abc.xxx() calls
    fn gen_abc_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "abstractmethod" => {
                // abc.abstractmethod(func) → mark as abstract (return func name)
                if let Some(arg) = args.first() {
                    format!("/* abstract: {} */ {{ unimplemented!() }}", self.gen_expr(arg))
                } else {
                    "{ unimplemented!() }".to_string()
                }
            }
            "abstractproperty" => {
                "/* abstract property */ unimplemented!()".to_string()
            }
            "get_cache_token" => {
                "0".to_string()
            }
            "register" => {
                // abc.register(subclass) → simplified no-op
                "// abc.register: virtual subclass registered (simplified)".to_string()
            }
            _ => format!("/* abc.{}: not implemented */", method),
        }
    }

    // ===== Standard library: ctypes module =====

    /// Map ctypes type name to Rust type string
    fn ctypes_type_to_rust(&self, name: &str) -> Option<&'static str> {
        match name {
            "c_int" => Some("i32"),
            "c_long" => Some("i64"),
            "c_float" => Some("f32"),
            "c_double" => Some("f64"),
            "c_char" => Some("char"),
            "c_bool" => Some("bool"),
            "c_int8" => Some("i8"),
            "c_int16" => Some("i16"),
            "c_int32" => Some("i32"),
            "c_int64" => Some("i64"),
            "c_uint8" => Some("u8"),
            "c_uint16" => Some("u16"),
            "c_uint32" => Some("u32"),
            "c_uint64" => Some("u64"),
            "c_size_t" => Some("usize"),
            "c_ssize_t" => Some("isize"),
            _ => None,
        }
    }

    /// Extract a Rust type string from an expression argument.
    /// Handles ctypes type constants (which gen_expr renders as "i32".to_string())
    /// and bare identifiers that are known Rust types.
    fn extract_rust_type_from_expr(&self, arg: &Expr) -> Option<String> {
        match arg {
            Expr::Attribute { target, name, .. } => {
                if let Expr::Ident { name: mod_name, .. } = target.as_ref() {
                    if mod_name == "ctypes" {
                        return self.ctypes_type_to_rust(name).map(|s| s.to_string());
                    }
                }
                None
            }
            Expr::Ident { name, .. } => {
                // Bare Rust type names: i32, i64, f32, f64, u8, etc.
                match name.as_str() {
                    "i8" | "i16" | "i32" | "i64" | "u8" | "u16" | "u32" | "u64" |
                    "f32" | "f64" | "usize" | "isize" | "bool" | "char" => Some(name.clone()),
                    _ => None,
                }
            }
            _ => None,
        }
    }

    /// Generate code for ctypes.xxx() calls
    fn gen_ctypes_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "sizeof" => {
                // ctypes.sizeof(type) → std::mem::size_of::<T>()
                if let Some(arg) = args.first() {
                    if let Some(rust_type) = self.extract_rust_type_from_expr(arg) {
                        return format!("std::mem::size_of::<{}>()", rust_type);
                    }
                    // Fallback: best-effort using the expression value as type name
                    return format!("std::mem::size_of_val(&{})", self.gen_expr(arg));
                }
                "/* ctypes.sizeof: missing arg */".to_string()
            }
            "cast" => {
                // ctypes.cast(obj, type) → obj as Type
                if args.len() >= 2 {
                    if let Some(rust_type) = self.extract_rust_type_from_expr(&args[1]) {
                        return format!("({}) as {}", self.gen_expr(&args[0]), rust_type);
                    }
                    return format!("({}) as {}", self.gen_expr(&args[0]), self.gen_expr(&args[1]));
                }
                "/* ctypes.cast: needs (obj, type) */".to_string()
            }
            "addressof" => {
                // ctypes.addressof(obj) → &obj as *const _ as usize
                if let Some(arg) = args.first() {
                    format!("(&{} as *const _ as usize)", self.gen_expr(arg))
                } else {
                    "/* ctypes.addressof: missing arg */".to_string()
                }
            }
            "byref" => {
                // ctypes.byref(obj) → &mut obj
                if let Some(arg) = args.first() {
                    format!("(&mut {})", self.gen_expr(arg))
                } else {
                    "/* ctypes.byref: missing arg */".to_string()
                }
            }
            "pointer" => {
                // ctypes.pointer(obj) → &obj as *const _
                if let Some(arg) = args.first() {
                    format!("(&{} as *const _)", self.gen_expr(arg))
                } else {
                    "/* ctypes.pointer: missing arg */".to_string()
                }
            }
            "memmove" => {
                // ctypes.memmove(dst, src, count) → std::ptr::copy
                if args.len() >= 3 {
                    format!("std::ptr::copy({}, {}, {})",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]), self.gen_expr(&args[2]))
                } else {
                    "/* ctypes.memmove: needs (dst, src, count) */".to_string()
                }
            }
            "memset" => {
                // ctypes.memset(dst, val, count) → std::ptr::write_bytes
                if args.len() >= 3 {
                    format!("std::ptr::write_bytes({}, {}, {})",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]), self.gen_expr(&args[2]))
                } else {
                    "/* ctypes.memset: needs (dst, val, count) */".to_string()
                }
            }
            "POINTER" => {
                // ctypes.POINTER(type) → *const T (as string)
                if let Some(arg) = args.first() {
                    if let Some(rust_type) = self.extract_rust_type_from_expr(arg) {
                        return format!("\"*const {}\".to_string()", rust_type);
                    }
                }
                "\"*const ()\".to_string()".to_string()
            }
            "CDLL" => {
                // ctypes.CDLL(name) → simplified (libloading would be needed at runtime)
                if let Some(arg) = args.first() {
                    format!("/* CDLL({}) — requires libloading crate */ ()", self.gen_expr(arg))
                } else {
                    "/* ctypes.CDLL: missing name */".to_string()
                }
            }
            "create_string_buffer" => {
                // ctypes.create_string_buffer(init, size?) → Vec<u8>
                match args.len() {
                    1 => format!("{}.as_bytes().to_vec()", self.gen_expr(&args[0])),
                    _ => format!("vec![0u8; {{ let __n = {}; __n }}]", self.gen_expr(&args[1])),
                }
            }
            "create_unicode_buffer" => {
                // ctypes.create_unicode_buffer(init, size?) → Vec<u16>
                match args.len() {
                    1 => format!("{}.encode_utf16().collect::<Vec<u16>>()", self.gen_expr(&args[0])),
                    _ => format!("vec![0u16; {{ let __n = {}; __n }}]", self.gen_expr(&args[1])),
                }
            }
            _ => format!("/* ctypes.{}: not implemented */", method),
        }
    }

    /// statistics module: mean, median, mode, stdev, variance, etc.
    fn gen_statistics_call(&self, method: &str, args: &[Expr]) -> String {
        let data = || -> String {
            args.first().map(|a| self.gen_expr(a)).unwrap_or_else(|| "vec![]".to_string())
        };
        match method {
            "mean" => {
                format!("{{ let __d: Vec<f64> = ({}).iter().map(|x| *x as f64).collect(); __d.iter().sum::<f64>() / __d.len() as f64 }}", data())
            }
            "median" => {
                format!("{{ let mut __d: Vec<f64> = ({}).iter().map(|x| *x as f64).collect(); __d.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal)); let __n = __d.len(); if __n == 0 {{ 0.0 }} else if __n % 2 == 1 {{ __d[__n / 2] }} else {{ (__d[__n / 2 - 1] + __d[__n / 2]) / 2.0 }} }}", data())
            }
            "mode" => {
                format!("{{ let __d: Vec<f64> = ({}).iter().map(|x| *x as f64).collect(); let mut __s = __d.clone(); __s.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal)); let mut __best_v = 0.0_f64; let mut __best_c = 0_usize; let mut __cur_v = 0.0_f64; let mut __cur_c = 0_usize; let mut __first = true; for __v in &__s {{ if __first || *__v != __cur_v {{ __cur_v = *__v; __cur_c = 1; __first = false; }} else {{ __cur_c += 1; }} if __cur_c > __best_c {{ __best_c = __cur_c; __best_v = __cur_v; }} }} __best_v }}", data())
            }
            "multimode" => {
                format!("{{ let __d: Vec<f64> = ({}).iter().map(|x| *x as f64).collect(); let mut __s = __d.clone(); __s.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal)); let mut __best_c = 0_usize; let mut __cur_v = 0.0_f64; let mut __cur_c = 0_usize; let mut __first = true; for __v in &__s {{ if __first || *__v != __cur_v {{ __cur_v = *__v; __cur_c = 1; __first = false; }} else {{ __cur_c += 1; }} if __cur_c > __best_c {{ __best_c = __cur_c; }} }} let mut __r: Vec<f64> = Vec::new(); __cur_v = 0.0_f64; __cur_c = 0_usize; __first = true; for __v in &__s {{ if __first || *__v != __cur_v {{ __cur_v = *__v; __cur_c = 1; __first = false; }} else {{ __cur_c += 1; }} if __cur_c == __best_c {{ __r.push(__cur_v); }} }} __r }}", data())
            }
            "variance" => {
                format!("{{ let __d: Vec<f64> = ({}).iter().map(|x| *x as f64).collect(); let __n = __d.len(); if __n < 2 {{ 0.0 }} else {{ let __mean = __d.iter().sum::<f64>() / __n as f64; __d.iter().map(|x| (x - __mean).powi(2)).sum::<f64>() / (__n - 1) as f64 }} }}", data())
            }
            "pvariance" => {
                format!("{{ let __d: Vec<f64> = ({}).iter().map(|x| *x as f64).collect(); let __n = __d.len(); if __n == 0 {{ 0.0 }} else {{ let __mean = __d.iter().sum::<f64>() / __n as f64; __d.iter().map(|x| (x - __mean).powi(2)).sum::<f64>() / __n as f64 }} }}", data())
            }
            "stdev" => {
                format!("{{ let __d: Vec<f64> = ({}).iter().map(|x| *x as f64).collect(); let __n = __d.len(); if __n < 2 {{ 0.0 }} else {{ let __mean = __d.iter().sum::<f64>() / __n as f64; let __v = __d.iter().map(|x| (x - __mean).powi(2)).sum::<f64>() / (__n - 1) as f64; __v.sqrt() }} }}", data())
            }
            "pstdev" => {
                format!("{{ let __d: Vec<f64> = ({}).iter().map(|x| *x as f64).collect(); let __n = __d.len(); if __n == 0 {{ 0.0 }} else {{ let __mean = __d.iter().sum::<f64>() / __n as f64; let __v = __d.iter().map(|x| (x - __mean).powi(2)).sum::<f64>() / __n as f64; __v.sqrt() }} }}", data())
            }
            "harmonic_mean" => {
                format!("{{ let __d: Vec<f64> = ({}).iter().map(|x| *x as f64).collect(); let __n = __d.len(); if __n == 0 {{ 0.0 }} else {{ let __sum_inv: f64 = __d.iter().map(|x| 1.0 / *x).sum(); __n as f64 / __sum_inv }} }}", data())
            }
            "geometric_mean" => {
                format!("{{ let __d: Vec<f64> = ({}).iter().map(|x| *x as f64).collect(); let __n = __d.len(); if __n == 0 {{ 0.0 }} else {{ let __sum_log: f64 = __d.iter().map(|x| x.ln()).sum(); (__sum_log / __n as f64).exp() }} }}", data())
            }
            "quantiles" => {
                let n_expr = args.get(1).map(|a| self.gen_expr(a)).unwrap_or_else(|| "4".to_string());
                format!("{{ let mut __d: Vec<f64> = ({}).iter().map(|x| *x as f64).collect(); __d.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal)); let __n: usize = {} as usize; let mut __r: Vec<f64> = Vec::new(); if __n > 1 && !__d.is_empty() {{ for __i in 1..__n {{ let __pos = (__i * __d.len()) as f64 / __n as f64; let __lo = __pos.floor() as usize; let __hi = __pos.ceil() as usize; let __lo = __lo.min(__d.len() - 1); let __hi = __hi.min(__d.len() - 1); let __frac = __pos - __pos.floor(); __r.push(__d[__lo] * (1.0 - __frac) + __d[__hi] * __frac); }} }} __r }}", data(), n_expr)
            }
            _ => format!("/* statistics.{}: not implemented */", method),
        }
    }

    /// random module: pseudo-random number generation backed by the `rand` crate.
    fn gen_random_call(&self, method: &str, args: &[Expr]) -> String {
        let arg0 = || -> String { args.first().map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string()) };
        let arg1 = || -> String { args.get(1).map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string()) };
        let arg2 = || -> String { args.get(2).map(|a| self.gen_expr(a)).unwrap_or_else(|| "1".to_string()) };
        match method {
            "seed" => "{ let _seed: Option<i64> = None; let _ = _seed; }".to_string(),
            "random" => "rand::random::<f64>()".to_string(),
            "uniform" => {
                format!("{{ let __a: f64 = ({}).into(); let __b: f64 = ({}).into(); __a + rand::random::<f64>() * (__b - __a) }}", arg0(), arg1())
            }
            "randint" => {
                format!("{{ let __a: i64 = {} as i64; let __b: i64 = {} as i64; let __span = (__b - __a + 1).max(1) as u64; (__a + (rand::random::<u64>() % __span) as i64) }}", arg0(), arg1())
            }
            "randrange" => {
                let start = arg0();
                let stop = arg1();
                let step = arg2();
                format!("{{ let __start: i64 = {s} as i64; let __stop: i64 = {e} as i64; let __step: i64 = {st} as i64; let __span = ((__stop - __start + __step - 1) / __step).max(0) as u64; __start + ((rand::random::<u64>() % __span) as i64) * __step }}", s = start, e = stop, st = step)
            }
            "choice" => {
                format!("{{ let __s = {}.clone(); let __i = rand::random::<usize>() % __s.len(); __s[__i].clone() }}", arg0())
            }
            "choices" => {
                let pop = arg0();
                let k = args.get(2).map(|a| self.gen_expr(a)).unwrap_or_else(|| "1".to_string());
                format!("{{ let __p = {pop}.clone(); let __k: usize = {k} as usize; let mut __out: Vec<_> = Vec::with_capacity(__k); for _ in 0..__k {{ let __i = rand::random::<usize>() % __p.len(); __out.push(__p[__i].clone()); }} __out }}", pop = pop, k = k)
            }
            "shuffle" => {
                format!("{{ let mut __s = {}.clone(); __s.shuffle(&mut rand::thread_rng()); __s }}", arg0())
            }
            "sample" => {
                let pop = arg0();
                let k = arg1();
                format!("{{ let mut __p = {pop}.clone(); let __k: usize = ({k} as usize).min(__p.len()); let mut __out: Vec<_> = Vec::with_capacity(__k); let mut __rng = rand::thread_rng(); for __i in 0..__k {{ let __j = __rng.gen_range(__i..__p.len()); __p.swap(__i, __j); __out.push(__p[__i].clone()); }} __out }}", pop = pop, k = k)
            }
            "gauss" | "normalvariate" => {
                format!("{{ let __mu: f64 = ({}).into(); let __sigma: f64 = ({}).into(); let __u1 = rand::random::<f64>().max(1e-10); let __u2 = rand::random::<f64>(); let __z0 = (-2.0 * __u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * __u2).cos(); __mu + __sigma * __z0 }}", arg0(), arg1())
            }
            "lognormvariate" => {
                format!("{{ let __mu: f64 = ({}).into(); let __sigma: f64 = ({}).into(); let __u1 = rand::random::<f64>().max(1e-10); let __u2 = rand::random::<f64>(); let __z0 = (-2.0 * __u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * __u2).cos(); (__mu + __sigma * __z0).exp() }}", arg0(), arg1())
            }
            "expovariate" => {
                format!("{{ let __l: f64 = ({}).into(); if __l == 0.0 {{ 0.0 }} else {{ -((1.0 - rand::random::<f64>()).max(1e-10)).ln() / __l }} }}", arg0())
            }
            "betavariate" => {
                format!("{{ let __a: f64 = ({}).into(); let __b: f64 = ({}).into(); let __g1 = {{ let __u = rand::random::<f64>().max(1e-10); -__u.ln() }} * __a; let __g2 = {{ let __u = rand::random::<f64>().max(1e-10); -__u.ln() }} * __b; if __g1 + __g2 == 0.0 {{ 0.0 }} else {{ __g1 / (__g1 + __g2) }} }}", arg0(), arg1())
            }
            "gammavariate" => {
                format!("{{ let __a: f64 = ({}).into(); let __b: f64 = ({}).into(); let __n = __a.floor() as usize; let mut __sum: f64 = 0.0; for _ in 0..__n {{ __sum += -((1.0 - rand::random::<f64>()).max(1e-10)).ln(); }} __sum * __b }}", arg0(), arg1())
            }
            "paretovariate" => {
                format!("{{ let __a: f64 = ({}).into(); if __a == 0.0 {{ 0.0 }} else {{ (1.0 - rand::random::<f64>()).max(1e-10).powf(-1.0 / __a) }} }}", arg0())
            }
            "weibullvariate" => {
                format!("{{ let __a: f64 = ({}).into(); let __b: f64 = ({}).into(); if __b == 0.0 {{ 0.0 }} else {{ __a * (-((1.0 - rand::random::<f64>()).max(1e-10)).ln()).powf(1.0 / __b) }} }}", arg0(), arg1())
            }
            "getrandbits" => {
                format!("{{ let __k: u32 = ({}).min(64) as u32; if __k == 0 {{ 0u64 }} else {{ rand::random::<u64>() & ((1u64 << __k) - 1) }} }}", arg0())
            }
            "getstate" => "vec![0u64; 8]".to_string(),
            "setstate" => "{ let _state = 0; }".to_string(),
            _ => format!("/* random.{}: not implemented */", method),
        }
    }

    /// operators module: functional equivalents of Python's operator module.
    fn gen_operators_call(&self, method: &str, args: &[Expr]) -> String {
        let arg0 = || -> String { args.first().map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string()) };
        let arg1 = || -> String { args.get(1).map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string()) };
        let arg2 = || -> String { args.get(2).map(|a| self.gen_expr(a)).unwrap_or_else(|| "\"\"".to_string()) };
        match method {
            "add" => format!("(({}) + ({}))", arg0(), arg1()),
            "sub" => format!("(({}) - ({}))", arg0(), arg1()),
            "mul" => format!("(({}) * ({}))", arg0(), arg1()),
            "truediv" => format!("(({}) / ({}))", arg0(), arg1()),
            "floordiv" => format!("((({}) / ({})) as i64)", arg0(), arg1()),
            "mod" | "mod_" => format!("(({}) % ({}))", arg0(), arg1()),
            "pow" | "pow_" => format!("(({}).powf({} as f64))", arg0(), arg1()),
            "neg" => format!("(-({}))", arg0()),
            "pos" => format!("({})", arg0()),
            "abs" => format!("({}).abs()", arg0()),
            "inv" | "invert" => format!("(!({}))", arg0()),
            "lshift" => format!("(({}) << ({}))", arg0(), arg1()),
            "rshift" => format!("(({}) >> ({}))", arg0(), arg1()),
            "and_" => format!("(({}) & ({}))", arg0(), arg1()),
            "or_" => format!("(({}) | ({}))", arg0(), arg1()),
            "xor" | "xor_" => format!("(({}) ^ ({}))", arg0(), arg1()),
            "concat" => format!("(({}).to_string() + &({}).to_string())", arg0(), arg1()),
            "contains" => format!("({}).contains(&({}))", arg0(), arg1()),
            "truth" => format!("(({}) != 0)", arg0()),
            "is_" => format!("std::ptr::eq(&({}), &({}))", arg0(), arg1()),
            "is_not" => format!("(!std::ptr::eq(&({}), &({})))", arg0(), arg1()),
            "index" => format!("(({}) as usize)", arg0()),
            "itemgetter" => format!("move |__obj: Vec<_>| __obj[{} as usize].clone()", arg0()),
            "attrgetter" => format!("move |__obj| __obj.{}.clone()", arg0()),
            "methodcaller" => {
                let name = arg0();
                format!("move |__obj| __obj.{}()", name.trim_matches('"'))
            }
            "comparison" => {
                format!("{{ let __a = {}; let __b = {}; let __op: String = ({}).to_string(); match __op.as_str() {{ \"==\" => __a == __b, \"!=\" => __a != __b, \"<\" => __a < __b, \">\" => __a > __b, \"<=\" => __a <= __b, \">=\" => __a >= __b, _ => false }} }}", arg0(), arg1(), arg2())
            }
            _ => format!("/* operators.{}: not implemented */", method),
        }
    }

    /// tempfile module: temporary file and directory creation.
    fn gen_tempfile_call(&self, method: &str, args: &[Expr]) -> String {
        let suffix = || -> String {
            args.first().map(|a| self.gen_expr(a)).unwrap_or_else(|| "\"\".to_string()".to_string())
        };
        let prefix = || -> String {
            args.get(1).map(|a| self.gen_expr(a)).unwrap_or_else(|| "\"tmp\".to_string()".to_string())
        };
        let dir = || -> String {
            args.get(2).map(|a| self.gen_expr(a)).unwrap_or_else(|| "std::env::temp_dir().to_string_lossy().to_string()".to_string())
        };
        match method {
            "gettempdir" => "std::env::temp_dir().to_string_lossy().to_string()".to_string(),
            "gettempdirb" => "std::env::temp_dir().to_path_buf().into_os_string().into_string().unwrap_or_default().into_bytes()".to_string(),
            "gettempprefix" => "\"tmp\".to_string()".to_string(),
            "mktemp" => {
                format!("{{ let __dir = std::path::PathBuf::from({d}); let __name = format!(\"{{}}{{}}{{}}\", {p}, std::process::id(), {s}); __dir.join(__name).to_string_lossy().to_string() }}",
                    d = dir(), p = prefix(), s = suffix())
            }
            "mkstemp" => {
                format!("{{ let __dir = std::path::PathBuf::from({d}); let __name = format!(\"{{}}{{}}{{}}\", {p}, std::process::id(), {s}); let __path = __dir.join(__name); let _ = std::fs::File::create(&__path); (0i32, __path.to_string_lossy().to_string()) }}",
                    d = dir(), p = prefix(), s = suffix())
            }
            "mkdtemp" => {
                format!("{{ let __dir = std::path::PathBuf::from({d}); let __name = format!(\"{{}}{{}}{{}}\", {p}, std::process::id(), {s}); let __path = __dir.join(__name); let _ = std::fs::create_dir(&__path); __path.to_string_lossy().to_string() }}",
                    d = dir(), p = prefix(), s = suffix())
            }
            "NamedTemporaryFile" | "TemporaryFile" | "SpooledTemporaryFile" => {
                format!("{{ let __dir = std::env::temp_dir(); let __name = format!(\"{{}}_{{}}{{}}\", \"tmp\", std::process::id(), {s}); let __path = __dir.join(__name); let _ = std::fs::File::create(&__path); __path.to_string_lossy().to_string() }}", s = suffix())
            }
            _ => format!("/* tempfile.{}: not implemented */", method),
        }
    }

    /// shutil module: high-level file and directory operations.
    fn gen_shutil_call(&self, method: &str, args: &[Expr]) -> String {
        let arg0 = || -> String { args.first().map(|a| self.gen_expr(a)).unwrap_or_else(|| "\"\"".to_string()) };
        let arg1 = || -> String { args.get(1).map(|a| self.gen_expr(a)).unwrap_or_else(|| "\"\"".to_string()) };
        let arg2 = || -> String { args.get(2).map(|a| self.gen_expr(a)).unwrap_or_else(|| "\"\"".to_string()) };
        match method {
            "copyfile" => format!("{{ let _ = std::fs::copy({}, {}); }}", arg0(), arg1()),
            "copy" | "copy2" => format!("{{ let _ = std::fs::copy({}, {}); }}", arg0(), arg1()),
            "copyfileobj" => {
                let length = args.get(2).map(|a| self.gen_expr(a)).unwrap_or_else(|| "16384".to_string());
                format!("{{ let __len: usize = {l}; let mut __buf = vec![0u8; __len]; let mut __src = {s}; let mut __dst = {d}; loop {{ let __n = std::io::Read::read(&mut __src, &mut __buf).unwrap_or(0); if __n == 0 {{ break; }} std::io::Write::write_all(&mut __dst, &__buf[..__n]).unwrap_or(()); }} }}", l = length, s = arg0(), d = arg1())
            }
            "move" => {
                format!("{{ let __src = {}; let __dst = {}; if std::fs::rename(&__src, &__dst).is_err() {{ let _ = std::fs::copy(&__src, &__dst); let _ = std::fs::remove_file(&__src); }} }}", arg0(), arg1())
            }
            "rmtree" => format!("{{ let _ = std::fs::remove_dir_all({}); }}", arg0()),
            "disk_usage" => {
                format!("{{ let __p = {}; let __meta = std::fs::metadata(&__p).unwrap(); (0u64, 0u64, __meta.len()) }}", arg0())
            }
            "which" => {
                format!("{{ let __cmd = {}; let __path = std::env::var(\"PATH\").unwrap_or_default(); let __found: Option<String> = __path.split(if cfg!(windows) {{ ';' }} else {{ ':' }}).map(|__d| std::path::Path::new(__d).join(&__cmd)).find(|__p| __p.exists()).map(|__p| __p.to_string_lossy().to_string()); __found.unwrap_or_default() }}", arg0())
            }
            "make_archive" => {
                format!("{{ let _base = {}; let _fmt = {}; let _root = {}; \"\".to_string() }}", arg0(), arg1(), arg2())
            }
            "unpack_archive" => format!("{{ let _fname = {}; let _dir = {}; }}", arg0(), arg1()),
            "get_archive_formats" => "vec![(\"zip\".to_string(), \"ZIP\".to_string()), (\"tar\".to_string(), \"TAR\".to_string())]".to_string(),
            "chown" => format!("{{ let _p = {}; let _u = 0; let _g = 0; }}", arg0()),
            _ => format!("/* shutil.{}: not implemented */", method),
        }
    }

    // ===== Standard library: time module =====

    /// Generate code for time.xxx() calls.
    /// Uses std::time for basic functions and chrono for date formatting.
    fn gen_time_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "time" => {
                // time.time() → current Unix time as f64
                "std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs_f64()".to_string()
            }
            "time_ns" => {
                // time.time_ns() → current Unix time in nanoseconds as i64
                "std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos() as i64".to_string()
            }
            "sleep" => {
                // time.sleep(secs) → std::thread::sleep
                if let Some(arg) = args.first() {
                    format!("std::thread::sleep(std::time::Duration::from_secs_f64({}))",
                        self.gen_expr(arg))
                } else {
                    "/* time.sleep: missing arg */".to_string()
                }
            }
            "perf_counter" => {
                // time.perf_counter() → monotonic seconds since base
                "VOX_TIME_BASE.elapsed().as_secs_f64()".to_string()
            }
            "perf_counter_ns" => {
                // time.perf_counter_ns() → monotonic nanoseconds since base
                "VOX_TIME_BASE.elapsed().as_nanos() as i64".to_string()
            }
            "monotonic" => {
                // time.monotonic() → monotonic seconds since base
                "VOX_TIME_BASE.elapsed().as_secs_f64()".to_string()
            }
            "monotonic_ns" => {
                // time.monotonic_ns() → monotonic nanoseconds since base
                "VOX_TIME_BASE.elapsed().as_nanos() as i64".to_string()
            }
            "ctime" => {
                // time.ctime(secs?) → "Wed Dec 31 19:00:00 1969" style string
                match args.len() {
                    0 => {
                        "chrono::Local::now().format(\"%a %b %e %H:%M:%S %Y\").to_string()".to_string()
                    }
                    _ => {
                        format!("chrono::DateTime::from_timestamp({} as i64, 0).map(|dt| dt.format(\"%a %b %e %H:%M:%S %Y\").to_string()).unwrap_or_default()",
                            self.gen_expr(&args[0]))
                    }
                }
            }
            "strftime" => {
                // time.strftime(fmt, time?) → format current/given time
                match args.len() {
                    1 => {
                        format!("chrono::Local::now().format(({}).as_str()).to_string()", self.gen_expr(&args[0]))
                    }
                    _ => {
                        format!("chrono::DateTime::from_timestamp({} as i64, 0).map(|dt| dt.format(({}).as_str()).to_string()).unwrap_or_default()",
                            self.gen_expr(&args[1]), self.gen_expr(&args[0]))
                    }
                }
            }
            "localtime" => {
                // time.localtime(secs?) → simplified local time as chrono DateTime
                match args.len() {
                    0 => "chrono::Local::now()".to_string(),
                    _ => {
                        format!("chrono::DateTime::from_timestamp({} as i64, 0).map(|dt| dt.with_timezone(&chrono::Local)).unwrap_or_else(|| chrono::Local::now())",
                            self.gen_expr(&args[0]))
                    }
                }
            }
            "gmtime" => {
                // time.gmtime(secs?) → simplified UTC time as chrono DateTime
                match args.len() {
                    0 => "chrono::Utc::now()".to_string(),
                    _ => {
                        format!("chrono::DateTime::from_timestamp({} as i64, 0).unwrap_or_else(|| chrono::Utc::now())",
                            self.gen_expr(&args[0]))
                    }
                }
            }
            "mktime" => {
                // time.mktime(t) → convert to Unix timestamp (expects a chrono-like value)
                if let Some(arg) = args.first() {
                    format!("({}).timestamp()", self.gen_expr(arg))
                } else {
                    "/* time.mktime: missing arg */".to_string()
                }
            }
            "process_time" | "thread_time" => {
                // Best-effort monotonic seconds
                "VOX_TIME_BASE.elapsed().as_secs_f64()".to_string()
            }
            "process_time_ns" | "thread_time_ns" => {
                "VOX_TIME_BASE.elapsed().as_nanos() as i64".to_string()
            }
            "clock" => {
                // Deprecated in Python; map to perf_counter
                "VOX_TIME_BASE.elapsed().as_secs_f64()".to_string()
            }
            _ => format!("/* time.{}: not implemented */", method),
        }
    }

    // ===== Standard library: datetime module =====

    /// Generate code for datetime.xxx() calls. Requires the chrono crate.
    fn gen_datetime_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "now" | "today" => {
                // datetime.now() / datetime.today() → chrono::Local::now()
                "chrono::Local::now()".to_string()
            }
            "utcnow" => {
                "chrono::Utc::now()".to_string()
            }
            "date" => {
                // datetime.date(year, month, day) → chrono::NaiveDate
                if args.len() >= 3 {
                    format!("chrono::NaiveDate::from_ymd_opt({} as i32, {} as u32, {} as u32).unwrap()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]), self.gen_expr(&args[2]))
                } else {
                    "/* datetime.date: needs (year, month, day) */".to_string()
                }
            }
            "time" => {
                // datetime.time(hour, min, sec) → chrono::NaiveTime
                match args.len() {
                    0 => "chrono::NaiveTime::from_hms_opt(0, 0, 0).unwrap()".to_string(),
                    1 => format!("chrono::NaiveTime::from_hms_opt({} as u32, 0, 0).unwrap()",
                        self.gen_expr(&args[0])),
                    2 => format!("chrono::NaiveTime::from_hms_opt({} as u32, {} as u32, 0).unwrap()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])),
                    _ => format!("chrono::NaiveTime::from_hms_opt({} as u32, {} as u32, {} as u32).unwrap()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]), self.gen_expr(&args[2])),
                }
            }
            "datetime" => {
                // datetime.datetime(year, month, day, hour, min, sec) → chrono::NaiveDateTime
                if args.len() >= 3 {
                    let y = self.gen_expr(&args[0]);
                    let mo = self.gen_expr(&args[1]);
                    let d = self.gen_expr(&args[2]);
                    let h = args.get(3).map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string());
                    let mi = args.get(4).map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string());
                    let s = args.get(5).map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string());
                    format!("chrono::NaiveDate::from_ymd_opt({} as i32, {} as u32, {} as u32).unwrap().and_hms_opt({} as u32, {} as u32, {} as u32).unwrap()",
                        y, mo, d, h, mi, s)
                } else {
                    "/* datetime.datetime: needs (year, month, day) */".to_string()
                }
            }
            "timedelta" => {
                // datetime.timedelta(days, seconds, microseconds) → chrono::Duration
                let days = args.get(0).map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string());
                let secs = args.get(1).map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string());
                let micros = args.get(2).map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string());
                format!("chrono::Duration::days({} as i64) + chrono::Duration::seconds({} as i64) + chrono::Duration::microseconds({} as i64)",
                    days, secs, micros)
            }
            "strptime" => {
                // datetime.strptime(date_string, format) → parse to NaiveDateTime (fallback to NaiveDate)
                if args.len() >= 2 {
                    format!("chrono::NaiveDateTime::parse_from_str(({}).as_str(), ({}).as_str()).or_else(|_| chrono::NaiveDate::parse_from_str(({}).as_str(), ({}).as_str()).map(|d| d.and_hms_opt(0, 0, 0).unwrap())).unwrap()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]),
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* datetime.strptime: needs (date_string, format) */".to_string()
                }
            }
            "strftime" => {
                // datetime.strftime(format) → format current time as string
                if let Some(arg) = args.first() {
                    format!("chrono::Local::now().format(({}).as_str()).to_string()", self.gen_expr(arg))
                } else {
                    "/* datetime.strftime: missing format */".to_string()
                }
            }
            "fromtimestamp" => {
                // datetime.fromtimestamp(secs) → Local DateTime
                if let Some(arg) = args.first() {
                    format!("chrono::DateTime::from_timestamp({} as i64, 0).map(|dt| dt.with_timezone(&chrono::Local)).unwrap_or_else(|| chrono::Local::now())",
                        self.gen_expr(arg))
                } else {
                    "/* datetime.fromtimestamp: missing arg */".to_string()
                }
            }
            "utcfromtimestamp" => {
                if let Some(arg) = args.first() {
                    format!("chrono::DateTime::from_timestamp({} as i64, 0).unwrap_or_else(|| chrono::Utc::now())",
                        self.gen_expr(arg))
                } else {
                    "/* datetime.utcfromtimestamp: missing arg */".to_string()
                }
            }
            _ => format!("/* datetime.{}: not implemented */", method),
        }
    }

    // ===== Standard library: copy module =====

    /// Generate code for copy.xxx() calls.
    /// Both copy and deepcopy map to .clone() (requires Clone trait).
    fn gen_copy_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "copy" => {
                // copy.copy(x) → x.clone() (shallow)
                if let Some(arg) = args.first() {
                    format!("({}).clone()", self.gen_expr(arg))
                } else {
                    "/* copy.copy: missing arg */".to_string()
                }
            }
            "deepcopy" => {
                // copy.deepcopy(x) → x.clone() (simplified — same as shallow)
                if let Some(arg) = args.first() {
                    format!("({}).clone()", self.gen_expr(arg))
                } else {
                    "/* copy.deepcopy: missing arg */".to_string()
                }
            }
            "register_copyable" => {
                // copy.register_copyable(type) → no-op
                "// copy.register_copyable: registered (simplified)".to_string()
            }
            "Error" => {
                "/* copy.Error: exception type */ ()".to_string()
            }
            _ => format!("/* copy.{}: not implemented */", method),
        }
    }

    // ===== Standard library: weakref module =====

    /// Generate code for weakref.xxx() calls.
    /// Simplified: weak refs become strong refs (Option/clone).
    fn gen_weakref_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "ref" => {
                // weakref.ref(obj) → Some(obj.clone())
                if let Some(arg) = args.first() {
                    format!("Some(({}).clone())", self.gen_expr(arg))
                } else {
                    "None".to_string()
                }
            }
            "proxy" => {
                // weakref.proxy(obj) → obj.clone() (simplified)
                if let Some(arg) = args.first() {
                    format!("({}).clone()", self.gen_expr(arg))
                } else {
                    "/* weakref.proxy: missing arg */".to_string()
                }
            }
            "getweakrefcount" => {
                // weakref.getweakrefcount(obj) → 0 (simplified)
                if let Some(_) = args.first() {
                    "0".to_string()
                } else {
                    "/* weakref.getweakrefcount: missing arg */".to_string()
                }
            }
            "getweakrefs" => {
                // weakref.getweakrefs(obj) → vec![] (simplified)
                if let Some(_) = args.first() {
                    "Vec::<String>::new()".to_string()
                } else {
                    "/* weakref.getweakrefs: missing arg */".to_string()
                }
            }
            "WeakValueDictionary" => {
                // weakref.WeakValueDictionary() → HashMap::new()
                "HashMap::<String, String>::new()".to_string()
            }
            "WeakKeyDictionary" => {
                // weakref.WeakKeyDictionary() → HashMap::new()
                "HashMap::<String, String>::new()".to_string()
            }
            "finalize" => {
                // weakref.finalize(obj, func, *args) → no-op finalizer (simplified)
                "/* weakref.finalize: registered (simplified) */ ()".to_string()
            }
            "ReferenceError" => {
                "/* weakref.ReferenceError: exception type */ ()".to_string()
            }
            _ => format!("/* weakref.{}: not implemented */", method),
        }
    }

    // ===== Standard library: sys, os, fs modules =====

    /// Check if a name is a recognized standard library module (sys, os, fs, math, cmath, numbers, decimals, fractions, etc.)
    fn is_std_module(&self, name: &str) -> bool {
        matches!(name, "sys" | "os" | "fs" | "io" | "env" | "math" | "cmath" | "numbers" | "decimals" | "fractions" | "time" | "datetime" | "string" | "re" | "funcs" | "statistics" | "random" | "operators" | "tempfile" | "shutil")
    }

    /// Check if (module, sub) is a recognized submodule pair (e.g., os.path)
    fn is_std_submodule(&self, module: &str, sub: &str) -> bool {
        matches!((module, sub), ("os", "path"))
    }

    /// Dispatch `module.method(args)` calls. Returns Some(code) if handled.
    fn gen_module_call(&self, module: &str, method: &str, args: &[Expr]) -> Option<String> {
        match module {
            "sys" => Some(self.gen_sys_call(method, args)),
            "os" => Some(self.gen_os_call(method, args)),
            "os.path" => Some(self.gen_os_path_call(method, args)),
            "fs" => Some(self.gen_fs_call(method, args)),
            "math" => Some(self.gen_math_call(method, args)),
            "cmath" => Some(self.gen_cmath_call(method, args)),
            "numbers" => Some(self.gen_numbers_call(method, args)),
            "decimals" => Some(self.gen_decimals_call(method, args)),
            "fractions" => Some(self.gen_fractions_call(method, args)),
            "statistics" => Some(self.gen_statistics_call(method, args)),
            "random" => Some(self.gen_random_call(method, args)),
            "operators" => Some(self.gen_operators_call(method, args)),
            "tempfile" => Some(self.gen_tempfile_call(method, args)),
            "shutil" => Some(self.gen_shutil_call(method, args)),
            _ => None,
        }
    }

    /// Dispatch `module.property` attribute access. Returns Some(code) if handled.
    fn gen_module_attr(&self, module: &str, attr: &str) -> Option<String> {
        match module {
            "sys" => self.gen_sys_attr(attr),
            "os" => self.gen_os_attr(attr),
            "math" => self.gen_math_attr(attr),
            "cmath" => self.gen_cmath_attr(attr),
            "numbers" => self.gen_numbers_attr(attr),
            "decimals" => self.gen_decimals_attr(attr),
            _ => None,
        }
    }

    /// Generate code for sys.<method>(args)
    fn gen_sys_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "exit" => {
                if let Some(arg) = args.first() {
                    format!("std::process::exit(({}) as i32)", self.gen_expr(arg))
                } else {
                    "std::process::exit(0)".to_string()
                }
            }
            "getrecursionlimit" => "128".to_string(),
            "setrecursionlimit" => {
                // no-op: Rust has no equivalent runtime recursion limit
                "()".to_string()
            }
            _ => format!("/* sys.{}: not implemented */", method),
        }
    }

    /// Generate code for sys.<attr> property access
    fn gen_sys_attr(&self, attr: &str) -> Option<String> {
        let code = match attr {
            "argv" => "std::env::args().collect::<Vec<String>>()".to_string(),
            "platform" => r#"if cfg!(windows) { "windows".to_string() } else { "linux".to_string() }"#.to_string(),
            "version" => "\"Vox 0.1.0\".to_string()".to_string(),
            "stdin" => "std::io::stdin()".to_string(),
            "stdout" => "std::io::stdout()".to_string(),
            "stderr" => "std::io::stderr()".to_string(),
            "path" => "vec![\".\".to_string()]".to_string(),
            "modules" => "HashMap::new()".to_string(),
            "maxsize" => "i64::MAX".to_string(),
            _ => return None,
        };
        Some(code)
    }

    /// Generate code for os.<method>(args)
    fn gen_os_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "getcwd" => {
                "std::env::current_dir().unwrap().to_string_lossy().to_string()".to_string()
            }
            "chdir" => {
                if let Some(arg) = args.first() {
                    format!("std::env::set_current_dir({}).unwrap()", self.gen_expr(arg))
                } else {
                    "/* os.chdir: missing path arg */ ()".to_string()
                }
            }
            "listdir" => {
                let path = args.first()
                    .map(|a| self.gen_expr(a))
                    .unwrap_or_else(|| "\".\".to_string()".to_string());
                format!(
                    "std::fs::read_dir({}).unwrap().map(|e| e.unwrap().file_name().to_string_lossy().to_string()).collect::<Vec<_>>()",
                    path
                )
            }
            "mkdir" => {
                if let Some(arg) = args.first() {
                    format!("std::fs::create_dir({}).unwrap()", self.gen_expr(arg))
                } else {
                    "/* os.mkdir: missing path arg */ ()".to_string()
                }
            }
            "makedirs" => {
                if let Some(arg) = args.first() {
                    format!("std::fs::create_dir_all({}).unwrap()", self.gen_expr(arg))
                } else {
                    "/* os.makedirs: missing path arg */ ()".to_string()
                }
            }
            "remove" | "unlink" => {
                if let Some(arg) = args.first() {
                    format!("std::fs::remove_file({}).unwrap()", self.gen_expr(arg))
                } else {
                    format!("/* os.{}: missing path arg */ ()", method)
                }
            }
            "rmdir" => {
                if let Some(arg) = args.first() {
                    format!("std::fs::remove_dir({}).unwrap()", self.gen_expr(arg))
                } else {
                    "/* os.rmdir: missing path arg */ ()".to_string()
                }
            }
            "rename" => {
                if args.len() >= 2 {
                    format!("std::fs::rename({}, {}).unwrap()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* os.rename: needs (old, new) */ ()".to_string()
                }
            }
            "environ" => {
                "std::env::vars().collect::<HashMap<String, String>>()".to_string()
            }
            "getenv" => {
                if let Some(key) = args.first() {
                    if args.len() >= 2 {
                        format!("std::env::var({}).unwrap_or({})",
                            self.gen_expr(key), self.gen_expr(&args[1]))
                    } else {
                        format!("std::env::var({}).unwrap_or_default()", self.gen_expr(key))
                    }
                } else {
                    "/* os.getenv: missing key */ \"\".to_string()".to_string()
                }
            }
            "setenv" => {
                if args.len() >= 2 {
                    format!("std::env::set_var({}, {})",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* os.setenv: needs (key, value) */ ()".to_string()
                }
            }
            _ => format!("/* os.{}: not implemented */", method),
        }
    }

    /// Generate code for os.<attr> property access
    fn gen_os_attr(&self, attr: &str) -> Option<String> {
        let code = match attr {
            "environ" => "std::env::vars().collect::<HashMap<String, String>>()".to_string(),
            "sep" => r#"if cfg!(windows) { "\\".to_string() } else { "/".to_string() }"#.to_string(),
            "linesep" => r#"if cfg!(windows) { "\r\n".to_string() } else { "\n".to_string() }"#.to_string(),
            "name" => r#"if cfg!(windows) { "nt".to_string() } else { "posix".to_string() }"#.to_string(),
            _ => return None,
        };
        Some(code)
    }

    /// Generate code for os.path.<method>(args)
    fn gen_os_path_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "exists" => {
                if let Some(arg) = args.first() {
                    format!("std::path::Path::new(&{}).exists()", self.gen_expr(arg))
                } else {
                    "/* os.path.exists: missing path */ false".to_string()
                }
            }
            "isfile" => {
                if let Some(arg) = args.first() {
                    format!("std::path::Path::new(&{}).is_file()", self.gen_expr(arg))
                } else {
                    "/* os.path.isfile: missing path */ false".to_string()
                }
            }
            "isdir" => {
                if let Some(arg) = args.first() {
                    format!("std::path::Path::new(&{}).is_dir()", self.gen_expr(arg))
                } else {
                    "/* os.path.isdir: missing path */ false".to_string()
                }
            }
            "join" => {
                if args.len() >= 2 {
                    format!("std::path::Path::new(&{}).join(&{}).to_string_lossy().to_string()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* os.path.join: needs (a, b) */ \"\".to_string()".to_string()
                }
            }
            "basename" => {
                if let Some(arg) = args.first() {
                    format!("std::path::Path::new(&{}).file_name().map(|f| f.to_string_lossy().to_string()).unwrap_or_default()",
                        self.gen_expr(arg))
                } else {
                    "/* os.path.basename: missing path */ \"\".to_string()".to_string()
                }
            }
            "dirname" => {
                if let Some(arg) = args.first() {
                    format!("std::path::Path::new(&{}).parent().map(|p| p.to_string_lossy().to_string()).unwrap_or_default()",
                        self.gen_expr(arg))
                } else {
                    "/* os.path.dirname: missing path */ \"\".to_string()".to_string()
                }
            }
            "split" => {
                if let Some(arg) = args.first() {
                    let p = self.gen_expr(arg);
                    format!(
                        "(std::path::Path::new(&{p}).parent().map(|d| d.to_string_lossy().to_string()).unwrap_or_default(), std::path::Path::new(&{p}).file_name().map(|f| f.to_string_lossy().to_string()).unwrap_or_default())",
                        p = p
                    )
                } else {
                    "/* os.path.split: missing path */ (\"\".to_string(), \"\".to_string())".to_string()
                }
            }
            _ => format!("/* os.path.{}: not implemented */", method),
        }
    }

    /// Generate code for fs.<method>(args)
    fn gen_fs_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "read_file" => {
                if let Some(arg) = args.first() {
                    format!("std::fs::read_to_string({}).unwrap()", self.gen_expr(arg))
                } else {
                    "/* fs.read_file: missing path */ \"\".to_string()".to_string()
                }
            }
            "write_file" => {
                if args.len() >= 2 {
                    format!("std::fs::write({}, {}).unwrap()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* fs.write_file: needs (path, content) */ ()".to_string()
                }
            }
            "append_file" => {
                if args.len() >= 2 {
                    format!(
                        "{{ use std::io::Write; let mut __f = std::fs::OpenOptions::new().append(true).create(true).open({}).unwrap(); __f.write_all({}.as_bytes()).unwrap(); }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])
                    )
                } else {
                    "/* fs.append_file: needs (path, content) */ ()".to_string()
                }
            }
            "copy" => {
                if args.len() >= 2 {
                    format!("std::fs::copy({}, {}).unwrap()", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* fs.copy: needs (src, dst) */ ()".to_string()
                }
            }
            "move_file" => {
                if args.len() >= 2 {
                    format!("std::fs::rename({}, {}).unwrap()", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* fs.move_file: needs (src, dst) */ ()".to_string()
                }
            }
            "exists" => {
                if let Some(arg) = args.first() {
                    format!("std::path::Path::new(&{}).exists()", self.gen_expr(arg))
                } else {
                    "/* fs.exists: missing path */ false".to_string()
                }
            }
            "is_file" => {
                if let Some(arg) = args.first() {
                    format!("std::path::Path::new(&{}).is_file()", self.gen_expr(arg))
                } else {
                    "/* fs.is_file: missing path */ false".to_string()
                }
            }
            "is_dir" => {
                if let Some(arg) = args.first() {
                    format!("std::path::Path::new(&{}).is_dir()", self.gen_expr(arg))
                } else {
                    "/* fs.is_dir: missing path */ false".to_string()
                }
            }
            _ => format!("/* fs.{}: not implemented */", method),
        }
    }

    // ===== Standard library: math, cmath, numbers, decimals, fractions =====

    /// Generate code for `math.<method>(args)`.
    fn gen_math_call(&self, method: &str, args: &[Expr]) -> String {
        let one = || -> String { args.first().map(|a| self.gen_expr(a)).unwrap_or_else(|| "0.0".to_string()) };
        let two = || -> String {
            args.get(1).map(|a| self.gen_expr(a)).unwrap_or_else(|| "0.0".to_string())
        };
        match method {
            "sqrt" => format!("({}).sqrt()", one()),
            "cbrt" => format!("({}).cbrt()", one()),
            "abs" | "fabs" => format!("({}).abs()", one()),
            "ceil" => format!("({}).ceil() as i64", one()),
            "floor" => format!("({}).floor() as i64", one()),
            "trunc" => format!("({}).trunc() as i64", one()),
            "round" => format!("({}).round() as i64", one()),
            "sin" => format!("({}).sin()", one()),
            "cos" => format!("({}).cos()", one()),
            "tan" => format!("({}).tan()", one()),
            "asin" => format!("({}).asin()", one()),
            "acos" => format!("({}).acos()", one()),
            "atan" => format!("({}).atan()", one()),
            "atan2" => format!("({}).atan2({})", one(), two()),
            "sinh" => format!("({}).sinh()", one()),
            "cosh" => format!("({}).cosh()", one()),
            "tanh" => format!("({}).tanh()", one()),
            "asinh" => format!("({}).asinh()", one()),
            "acosh" => format!("({}).acosh()", one()),
            "atanh" => format!("({}).atanh()", one()),
            "exp" => format!("({}).exp()", one()),
            "exp2" => format!("({}).exp2()", one()),
            "expm1" => format!("({}).exp_m1()", one()),
            "log" => {
                if args.len() >= 2 {
                    format!("(({}).log({}))", one(), two())
                } else {
                    format!("({}).ln()", one())
                }
            }
            "log2" => format!("({}).log2()", one()),
            "log10" => format!("({}).log10()", one()),
            "log1p" => format!("({}).ln_1p()", one()),
            "pow" | "power" => format!("({}).powf({})", one(), two()),
            "hypot" => format!("({}).hypot({})", one(), two()),
            "fmod" => format!("({}).rem_euclid({})", one(), two()),
            "copysign" => format!("({}).copysign({})", one(), two()),
            "modf" => format!("{{ let __x = {}; (__x.trunc(), __x.fract()) }}", one()),
            "frexp" => format!("{{ let __x = {}; let __e = __x.abs().log2().floor() as i32 + 1; (__x / 2f64.powi(__e), __e) }}", one()),
            "ldexp" => format!("({}).mul(2f64.powi({} as i32))", one(), two()),
            "isnan" => format!("({}).is_nan()", one()),
            "isinf" => format!("({}).is_infinite()", one()),
            "isfinite" => format!("({}).is_finite()", one()),
            "isqrt" => format!("(({}).max(0) as f64).sqrt() as i64", one()),
            "gcd" => format!("vox_math_gcd({} as i64, {} as i64)", one(), two()),
            "lcm" => format!("vox_math_lcm({} as i64, {} as i64)", one(), two()),
            "factorial" => format!("vox_math_factorial({} as u64)", one()),
            "perm" => {
                if args.len() >= 2 {
                    format!("vox_math_perm({} as u64, {} as u64)", one(), two())
                } else {
                    format!("vox_math_factorial({} as u64)", one())
                }
            }
            "comb" => format!("vox_math_comb({} as u64, {} as u64)", one(), two()),
            "degrees" => format!("({}).to_degrees()", one()),
            "radians" => format!("({}).to_radians()", one()),
            "gamma" => format!("vox_math_gamma({})", one()),
            "lgamma" => format!("vox_math_lgamma({})", one()),
            "erf" => format!("vox_math_erf({})", one()),
            "erfc" => format!("(1.0 - vox_math_erf({}))", one()),
            "fsum" => format!("{{ let __v: Vec<f64> = vec![{}]; __v.iter().sum() }}", one()),
            "prod" => format!("{{ let __v: Vec<f64> = vec![{}]; __v.iter().product() }}", one()),
            "dist" => format!("vox_math_dist(&[{}], &[{}])", one(), two()),
            "remainder" => format!("({}).rem_euclid({})", one(), two()),
            "isclose" => {
                if args.len() >= 2 {
                    format!("(({} - {}).abs() < 1e-9)", one(), two())
                } else {
                    "false".to_string()
                }
            }
            _ => format!("/* math.{}: not implemented */", method),
        }
    }

    /// Generate code for `math.<attr>` constant access.
    fn gen_math_attr(&self, attr: &str) -> Option<String> {
        Some(match attr {
            "pi" => "std::f64::consts::PI".to_string(),
            "e" => "std::f64::consts::E".to_string(),
            "tau" => "std::f64::consts::TAU".to_string(),
            "inf" => "f64::INFINITY".to_string(),
            "nan" => "f64::NAN".to_string(),
            _ => return None,
        })
    }

    /// Generate code for `cmath.<method>(args)`.
    fn gen_cmath_call(&self, method: &str, args: &[Expr]) -> String {
        let one = || -> String { args.first().map(|a| self.gen_expr(a)).unwrap_or_else(|| "VoxComplex::new(0.0, 0.0)".to_string()) };
        let two = || -> String { args.get(1).map(|a| self.gen_expr(a)).unwrap_or_else(|| "VoxComplex::new(0.0, 0.0)".to_string()) };
        match method {
            "sqrt" => format!("VoxComplex::sqrt(&{})", one()),
            "exp" => format!("VoxComplex::exp(&{})", one()),
            "log" => format!("VoxComplex::log(&{})", one()),
            "log10" => format!("VoxComplex::log10(&{})", one()),
            "sin" => format!("VoxComplex::sin(&{})", one()),
            "cos" => format!("VoxComplex::cos(&{})", one()),
            "tan" => format!("VoxComplex::tan(&{})", one()),
            "asin" => format!("VoxComplex::asin(&{})", one()),
            "acos" => format!("VoxComplex::acos(&{})", one()),
            "atan" => format!("VoxComplex::atan(&{})", one()),
            "sinh" => format!("VoxComplex::sinh(&{})", one()),
            "cosh" => format!("VoxComplex::cosh(&{})", one()),
            "tanh" => format!("VoxComplex::tanh(&{})", one()),
            "asinh" => format!("VoxComplex::asinh(&{})", one()),
            "acosh" => format!("VoxComplex::acosh(&{})", one()),
            "atanh" => format!("VoxComplex::atanh(&{})", one()),
            "pow" | "power" => format!("VoxComplex::pow(&{}, &{})", one(), two()),
            "phase" => format!("VoxComplex::phase(&{})", one()),
            "polar" => format!("VoxComplex::polar(&{})", one()),
            "rect" => format!("VoxComplex::rect({}, {})", one(), two()),
            "isnan" => format!("VoxComplex::isnan(&{})", one()),
            "isinf" => format!("VoxComplex::isinf(&{})", one()),
            "isfinite" => format!("VoxComplex::isfinite(&{})", one()),
            "isclose" => format!("VoxComplex::isclose(&{}, &{})", one(), two()),
            _ => format!("/* cmath.{}: not implemented */", method),
        }
    }

    /// Generate code for `cmath.<attr>` constant access.
    fn gen_cmath_attr(&self, attr: &str) -> Option<String> {
        Some(match attr {
            "pi" => "std::f64::consts::PI".to_string(),
            "e" => "std::f64::consts::E".to_string(),
            "tau" => "std::f64::consts::TAU".to_string(),
            "inf" => "f64::INFINITY".to_string(),
            "nan" => "f64::NAN".to_string(),
            "j" => "VoxComplex::new(0.0, 1.0)".to_string(),
            _ => return None,
        })
    }

    /// Generate code for `numbers.<method>(args)` (abstract base classes).
    fn gen_numbers_call(&self, method: &str, _args: &[Expr]) -> String {
        match method {
            "Number" | "Complex" | "Real" | "Rational" | "Integral" => {
                "vox_numbers_abc()".to_string()
            }
            _ => format!("/* numbers.{}: not implemented */", method),
        }
    }

    /// Generate code for `numbers.<attr>` constant access.
    fn gen_numbers_attr(&self, attr: &str) -> Option<String> {
        match attr {
            "Number" | "Complex" | "Real" | "Rational" | "Integral" => {
                Some("vox_numbers_abc()".to_string())
            }
            _ => None,
        }
    }

    /// Generate code for `decimals.<attr>` property access (no parens).
    fn gen_decimals_attr(&self, attr: &str) -> Option<String> {
        let code = match attr {
            "MAX_PREC" => "vox_decimals_max_prec()",
            "MAX_EMAX" => "vox_decimals_max_emax()",
            "MIN_EMIN" => "vox_decimals_min_emin()",
            "HAVE_CONTEXTVAR" => "true",
            "HAVE_THREADS" => "true",
            _ => return None,
        };
        Some(code.to_string())
    }

    /// Generate code for `decimals.<method>(args)`.
    fn gen_decimals_call(&self, method: &str, args: &[Expr]) -> String {
        let one = || -> String { args.first().map(|a| self.gen_expr(a)).unwrap_or_else(|| "\"0\"".to_string()) };
        match method {
            "Decimal" => format!("VoxDecimal::from({})", one()),
            "getcontext" => "vox_decimals_getcontext()".to_string(),
            "setcontext" => format!("vox_decimals_setcontext({})", one()),
            "localcontext" => format!("vox_decimals_localcontext({})", one()),
            "MAX_PREC" => "vox_decimals_max_prec()".to_string(),
            "MAX_EMAX" => "vox_decimals_max_emax()".to_string(),
            "MIN_EMIN" => "vox_decimals_min_emin()".to_string(),
            "HAVE_CONTEXTVAR" => "true".to_string(),
            "HAVE_THREADS" => "true".to_string(),
            _ => format!("/* decimals.{}: not implemented */", method),
        }
    }

    /// Generate code for `fractions.<method>(args)`.
    fn gen_fractions_call(&self, method: &str, args: &[Expr]) -> String {
        let one = || -> String { args.first().map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string()) };
        let two = || -> String { args.get(1).map(|a| self.gen_expr(a)).unwrap_or_else(|| "1".to_string()) };
        match method {
            "Fraction" => {
                if args.len() >= 2 {
                    format!("VoxFraction::new({} as i64, {} as i64)", one(), two())
                } else {
                    format!("VoxFraction::from({})", one())
                }
            }
            "gcd" => format!("vox_fractions_gcd({} as i64, {} as i64)", one(), two()),
            _ => format!("/* fractions.{}: not implemented */", method),
        }
    }

    /// Emit helper structs and functions for math/cmath/decimals/fractions modules.
    fn emit_stdlib_helpers(&mut self) {
        self.emit_line("");
        self.emit_line("// === Vox stdlib helpers: VoxComplex, VoxDecimal, VoxFraction, math functions ===");
        self.emit_line("");
        self.emit_raw(r#"// --- VoxComplex: complex number support for cmath module ---
#[derive(Debug, Clone, Copy)]
pub struct VoxComplex {
    pub re: f64,
    pub im: f64,
}

impl VoxComplex {
    pub fn new(re: f64, im: f64) -> Self { VoxComplex { re, im } }
    pub fn from_real(x: f64) -> Self { VoxComplex { re: x, im: 0.0 } }
    pub fn abs(&self) -> f64 { self.re.hypot(self.im) }
    pub fn phase(&self) -> f64 { self.im.atan2(self.re) }
    pub fn polar(&self) -> (f64, f64) { (self.abs(), self.phase()) }
    pub fn rect(r: f64, theta: f64) -> Self { VoxComplex { re: r * theta.cos(), im: r * theta.sin() } }
    pub fn conjugate(&self) -> Self { VoxComplex { re: self.re, im: -self.im } }
    pub fn sqrt(c: &VoxComplex) -> VoxComplex {
        let r = c.abs();
        let re = ((r + c.re) / 2.0).max(0.0).sqrt();
        let im = ((r - c.re) / 2.0).max(0.0).sqrt().copysign(c.im);
        VoxComplex { re, im }
    }
    pub fn exp(c: &VoxComplex) -> VoxComplex {
        let e = c.re.exp();
        VoxComplex { re: e * c.im.cos(), im: e * c.im.sin() }
    }
    pub fn log(c: &VoxComplex) -> VoxComplex {
        VoxComplex { re: c.abs().ln(), im: c.phase() }
    }
    pub fn log10(c: &VoxComplex) -> VoxComplex {
        VoxComplex { re: c.abs().log10(), im: c.phase() }
    }
    pub fn sin(c: &VoxComplex) -> VoxComplex {
        VoxComplex { re: c.re.sin() * c.im.cosh(), im: c.re.cos() * c.im.sinh() }
    }
    pub fn cos(c: &VoxComplex) -> VoxComplex {
        VoxComplex { re: c.re.cos() * c.im.cosh(), im: -(c.re.sin() * c.im.sinh()) }
    }
    pub fn tan(c: &VoxComplex) -> VoxComplex {
        let s = Self::sin(c);
        let co = Self::cos(c);
        Self::div(&s, &co)
    }
    pub fn asin(c: &VoxComplex) -> VoxComplex {
        let i = VoxComplex::new(0.0, 1.0);
        let one = VoxComplex::new(1.0, 0.0);
        let inner = Self::sub(&one, &Self::mul(c, c));
        let sqrt_inner = Self::sqrt(&inner);
        let val = Self::sub(&Self::mul(&i, c), &sqrt_inner);
        Self::mul(&Self::sqrt(&val), &i.neg())
    }
    pub fn acos(c: &VoxComplex) -> VoxComplex {
        let i = VoxComplex::new(0.0, 1.0);
        let one = VoxComplex::new(1.0, 0.0);
        let inner = Self::sub(&one, &Self::mul(c, c));
        let sqrt_inner = Self::sqrt(&inner);
        let val = Self::add(c, &Self::mul(&i, &sqrt_inner));
        Self::mul(&Self::log(&val), &i)
    }
    pub fn atan(c: &VoxComplex) -> VoxComplex {
        let i = VoxComplex::new(0.0, 1.0);
        let two_i = VoxComplex::new(0.0, 2.0);
        let num = Self::sub(&i, c);
        let den = Self::add(&i, c);
        Self::div(&Self::log(&Self::div(&num, &den)), &two_i)
    }
    pub fn sinh(c: &VoxComplex) -> VoxComplex {
        VoxComplex { re: c.re.sinh() * c.im.cos(), im: c.re.cosh() * c.im.sin() }
    }
    pub fn cosh(c: &VoxComplex) -> VoxComplex {
        VoxComplex { re: c.re.cosh() * c.im.cos(), im: c.re.sinh() * c.im.sin() }
    }
    pub fn tanh(c: &VoxComplex) -> VoxComplex {
        let s = Self::sinh(c);
        let ch = Self::cosh(c);
        Self::div(&s, &ch)
    }
    pub fn asinh(c: &VoxComplex) -> VoxComplex {
        Self::mul(&Self::sqrt(&Self::add(&Self::mul(c, c), &VoxComplex::new(1.0, 0.0))), c)
            .log_sh()
    }
    fn log_sh(self) -> VoxComplex { Self::log(&self) }
    pub fn acosh(c: &VoxComplex) -> VoxComplex {
        let one = VoxComplex::new(1.0, 0.0);
        let inner = Self::sub(&Self::mul(c, c), &one);
        Self::add(c, &Self::sqrt(&inner)).log_sh()
    }
    pub fn atanh(c: &VoxComplex) -> VoxComplex {
        let one = VoxComplex::new(1.0, 0.0);
        let num = Self::add(&one, c);
        let den = Self::sub(&one, c);
        Self::mul(&Self::log(&Self::div(&num, &den)), &VoxComplex::new(0.5, 0.0))
    }
    pub fn pow(a: &VoxComplex, b: &VoxComplex) -> VoxComplex {
        Self::exp(&Self::mul(b, &Self::log(a)))
    }
    pub fn add(a: &VoxComplex, b: &VoxComplex) -> VoxComplex { VoxComplex { re: a.re + b.re, im: a.im + b.im } }
    pub fn sub(a: &VoxComplex, b: &VoxComplex) -> VoxComplex { VoxComplex { re: a.re - b.re, im: a.im - b.im } }
    pub fn mul(a: &VoxComplex, b: &VoxComplex) -> VoxComplex {
        VoxComplex { re: a.re * b.re - a.im * b.im, im: a.re * b.im + a.im * b.re }
    }
    pub fn div(a: &VoxComplex, b: &VoxComplex) -> VoxComplex {
        let d = b.re * b.re + b.im * b.im;
        if d == 0.0 { return VoxComplex::new(f64::NAN, f64::NAN); }
        VoxComplex { re: (a.re * b.re + a.im * b.im) / d, im: (a.im * b.re - a.re * b.im) / d }
    }
    pub fn neg(self) -> VoxComplex { VoxComplex { re: -self.re, im: -self.im } }
    pub fn isnan(c: &VoxComplex) -> bool { c.re.is_nan() || c.im.is_nan() }
    pub fn isinf(c: &VoxComplex) -> bool { c.re.is_infinite() || c.im.is_infinite() }
    pub fn isfinite(c: &VoxComplex) -> bool { c.re.is_finite() && c.im.is_finite() }
    pub fn isclose(a: &VoxComplex, b: &VoxComplex) -> bool {
        (a.re - b.re).abs() < 1e-9 && (a.im - b.im).abs() < 1e-9
    }
}

impl std::ops::Add for VoxComplex {
    type Output = VoxComplex;
    fn add(self, other: VoxComplex) -> VoxComplex { VoxComplex::add(&self, &other) }
}
impl std::ops::Sub for VoxComplex {
    type Output = VoxComplex;
    fn sub(self, other: VoxComplex) -> VoxComplex { VoxComplex::sub(&self, &other) }
}
impl std::ops::Mul for VoxComplex {
    type Output = VoxComplex;
    fn mul(self, other: VoxComplex) -> VoxComplex { VoxComplex::mul(&self, &other) }
}
impl std::ops::Div for VoxComplex {
    type Output = VoxComplex;
    fn div(self, other: VoxComplex) -> VoxComplex { VoxComplex::div(&self, &other) }
}
impl std::ops::Neg for VoxComplex {
    type Output = VoxComplex;
    fn neg(self) -> VoxComplex { VoxComplex { re: -self.re, im: -self.im } }
}
impl From<f64> for VoxComplex {
    fn from(x: f64) -> Self { VoxComplex { re: x, im: 0.0 } }
}
impl From<i64> for VoxComplex {
    fn from(x: i64) -> Self { VoxComplex { re: x as f64, im: 0.0 } }
}
impl std::fmt::Display for VoxComplex {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        if self.im >= 0.0 {
            write!(f, "({}+{}j)", self.re, self.im)
        } else {
            write!(f, "({}{}j)", self.re, self.im)
        }
    }
}

// --- VoxDecimal: simplified decimal support ---
#[derive(Debug, Clone)]
pub struct VoxDecimal {
    pub value: String,
}

impl VoxDecimal {
    pub fn new(s: &str) -> Self { VoxDecimal { value: s.to_string() } }
    pub fn to_f64(&self) -> f64 { self.value.parse().unwrap_or(0.0) }
}

impl From<&str> for VoxDecimal {
    fn from(s: &str) -> Self { VoxDecimal::new(s) }
}
impl From<String> for VoxDecimal {
    fn from(s: String) -> Self { VoxDecimal::new(&s) }
}
impl From<f64> for VoxDecimal {
    fn from(x: f64) -> Self { VoxDecimal { value: x.to_string() } }
}
impl From<i64> for VoxDecimal {
    fn from(x: i64) -> Self { VoxDecimal { value: x.to_string() } }
}
impl std::ops::Add for VoxDecimal {
    type Output = VoxDecimal;
    fn add(self, other: VoxDecimal) -> VoxDecimal {
        VoxDecimal { value: (self.to_f64() + other.to_f64()).to_string() }
    }
}
impl std::ops::Sub for VoxDecimal {
    type Output = VoxDecimal;
    fn sub(self, other: VoxDecimal) -> VoxDecimal {
        VoxDecimal { value: (self.to_f64() - other.to_f64()).to_string() }
    }
}
impl std::ops::Mul for VoxDecimal {
    type Output = VoxDecimal;
    fn mul(self, other: VoxDecimal) -> VoxDecimal {
        VoxDecimal { value: (self.to_f64() * other.to_f64()).to_string() }
    }
}
impl std::ops::Div for VoxDecimal {
    type Output = VoxDecimal;
    fn div(self, other: VoxDecimal) -> VoxDecimal {
        let d = other.to_f64();
        if d == 0.0 { return VoxDecimal { value: "NaN".to_string() }; }
        VoxDecimal { value: (self.to_f64() / d).to_string() }
    }
}
impl std::fmt::Display for VoxDecimal {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Decimal('{}')", self.value)
    }
}

pub fn vox_decimals_getcontext() -> String { "VoxDecimalContext".to_string() }
pub fn vox_decimals_setcontext(_ctx: String) { }
pub fn vox_decimals_localcontext(_ctx: String) -> String { "VoxDecimalContext".to_string() }
pub fn vox_decimals_max_prec() -> u32 { 999999999 }
pub fn vox_decimals_max_emax() -> i64 { 999999999 }
pub fn vox_decimals_min_emin() -> i64 { -999999999 }

// --- VoxFraction: rational number support ---
#[derive(Debug, Clone, Copy)]
pub struct VoxFraction {
    pub numer: i64,
    pub denom: i64,
}

impl VoxFraction {
    pub fn new(numer: i64, denom: i64) -> Self {
        if denom == 0 { return VoxFraction { numer: 0, denom: 1 }; }
        let g = vox_fractions_gcd(numer.abs(), denom.abs());
        let (n, d) = (numer / g, denom / g);
        if d < 0 { VoxFraction { numer: -n, denom: -d } } else { VoxFraction { numer: n, denom: d } }
    }
    pub fn to_f64(&self) -> f64 { self.numer as f64 / self.denom as f64 }
}

impl From<i64> for VoxFraction {
    fn from(x: i64) -> Self { VoxFraction { numer: x, denom: 1 } }
}
impl From<f64> for VoxFraction {
    fn from(x: f64) -> Self {
        if x.is_nan() || x.is_infinite() { return VoxFraction { numer: 0, denom: 1 }; }
        let denom = 1_000_000i64;
        let numer = (x * denom as f64).round() as i64;
        VoxFraction::new(numer, denom)
    }
}
impl std::ops::Add for VoxFraction {
    type Output = VoxFraction;
    fn add(self, other: VoxFraction) -> VoxFraction {
        VoxFraction::new(self.numer * other.denom + other.numer * self.denom, self.denom * other.denom)
    }
}
impl std::ops::Sub for VoxFraction {
    type Output = VoxFraction;
    fn sub(self, other: VoxFraction) -> VoxFraction {
        VoxFraction::new(self.numer * other.denom - other.numer * self.denom, self.denom * other.denom)
    }
}
impl std::ops::Mul for VoxFraction {
    type Output = VoxFraction;
    fn mul(self, other: VoxFraction) -> VoxFraction {
        VoxFraction::new(self.numer * other.numer, self.denom * other.denom)
    }
}
impl std::ops::Div for VoxFraction {
    type Output = VoxFraction;
    fn div(self, other: VoxFraction) -> VoxFraction {
        if other.numer == 0 { return VoxFraction { numer: 0, denom: 1 }; }
        VoxFraction::new(self.numer * other.denom, self.denom * other.numer)
    }
}
impl std::fmt::Display for VoxFraction {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Fraction({}, {})", self.numer, self.denom)
    }
}

pub fn vox_fractions_gcd(a: i64, b: i64) -> i64 {
    let mut a = a.abs();
    let mut b = b.abs();
    while b != 0 { let t = b; b = a % b; a = t; }
    a
}

// --- numbers module ABCs (stub) ---
pub fn vox_numbers_abc() -> &'static str { "VoxNumberABC" }

// --- math helper functions ---
pub fn vox_math_gcd(a: i64, b: i64) -> i64 {
    let mut a = a.abs();
    let mut b = b.abs();
    while b != 0 { let t = b; b = a % b; a = t; }
    a
}
pub fn vox_math_lcm(a: i64, b: i64) -> i64 {
    if a == 0 || b == 0 { return 0; }
    (a / vox_math_gcd(a, b)) * b
}
pub fn vox_math_factorial(n: u64) -> u64 {
    (1..=n).product()
}
pub fn vox_math_perm(n: u64, k: u64) -> u64 {
    if k > n { return 0; }
    (n - k + 1..=n).product()
}
pub fn vox_math_comb(n: u64, k: u64) -> u64 {
    if k > n { return 0; }
    let k = k.min(n - k);
    let mut result: u64 = 1;
    for i in 0..k {
        result = result * (n - i) / (i + 1);
    }
    result
}
pub fn vox_math_dist(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| (x - y).powi(2)).sum::<f64>().sqrt()
}
pub fn vox_math_gamma(x: f64) -> f64 {
    // Lanczos approximation
    if x < 0.5 {
        std::f64::consts::PI / ((std::f64::consts::PI * x).sin() * vox_math_gamma(1.0 - x))
    } else {
        let g = 7.0;
        let c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028,
                 771.32342877765313, -176.61502916214059, 12.507343278686905,
                 -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
        let x = x - 1.0;
        let mut a = c[0];
        let mut t = x + g + 0.5;
        for i in 1..9 { a += c[i] / (x + i as f64); }
        (2.0 * std::f64::consts::PI).sqrt() * t.powf(x + 0.5) * (-t).exp() * a
    }
}
pub fn vox_math_lgamma(x: f64) -> f64 { vox_math_gamma(x).abs().ln() }
pub fn vox_math_erf(x: f64) -> f64 {
    // Abramowitz and Stegun approximation
    let sign = if x < 0.0 { -1.0 } else { 1.0 };
    let x = x.abs();
    let a1 =  0.254829592;
    let a2 = -0.284496736;
    let a3 =  1.421413741;
    let a4 = -1.453152027;
    let a5 =  1.061405429;
    let p  =  0.3275911;
    let t = 1.0 / (1.0 + p * x);
    let y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * (-x * x).exp();
    sign * y
}
"#);
        self.emit_line("");
    }

    /// Emit logging support structs so generated code compiles when logging module is used
    fn emit_logging_support(&mut self) {
        self.emit_line("");
        self.emit_line("// === Vox Logging support (auto-generated) ===");
        self.emit_line("");
        self.emit_raw(r#"#[derive(Debug)]
pub struct VoxLogger {
    pub name: String,
}

impl VoxLogger {
    pub fn new(name: String) -> Self {
        VoxLogger { name }
    }
    pub fn debug(&self, msg: impl std::fmt::Display) {
        eprintln!("[DEBUG] {}: {}", self.name, msg);
    }
    pub fn info(&self, msg: impl std::fmt::Display) {
        eprintln!("[INFO] {}: {}", self.name, msg);
    }
    pub fn warning(&self, msg: impl std::fmt::Display) {
        eprintln!("[WARNING] {}: {}", self.name, msg);
    }
    pub fn warn(&self, msg: impl std::fmt::Display) {
        self.warning(msg);
    }
    pub fn error(&self, msg: impl std::fmt::Display) {
        eprintln!("[ERROR] {}: {}", self.name, msg);
    }
    pub fn critical(&self, msg: impl std::fmt::Display) {
        eprintln!("[CRITICAL] {}: {}", self.name, msg);
    }
    pub fn fatal(&self, msg: impl std::fmt::Display) {
        self.critical(msg);
    }
}

pub struct VoxStreamHandler;

pub struct VoxFileHandler {
    pub filename: String,
}

impl VoxFileHandler {
    pub fn new(filename: String) -> Self {
        VoxFileHandler { filename }
    }
}

pub struct VoxFormatter {
    pub fmt: String,
}

impl VoxFormatter {
    pub fn new(fmt: String) -> Self {
        VoxFormatter { fmt }
    }
}
"#);
        self.emit_line("");
    }

    /// Emit doc registry for inspect.doc / reflect.doc runtime lookup.
    fn emit_doc_registry(&mut self) {
        if self.doc_registry.is_empty() {
            return;
        }
        self.emit_line("");
        self.emit_line("// === Vox Doc Registry ===");
        self.emit_line("static VOX_DOC_REGISTRY: std::sync::LazyLock<std::collections::HashMap<&'static str, &'static str>> = std::sync::LazyLock::new(|| {");
        self.indent_level += 1;
        self.emit_line("let mut m = std::collections::HashMap::new();");
        let names: Vec<String> = self.doc_registry.keys().cloned().collect();
        for name in &names {
            if let Some(doc) = self.doc_registry.get(name) {
                let escaped = self.escape_string(doc);
                self.emit_line(&format!("m.insert(\"{}\", \"{}\");", name, escaped));
            }
        }
        self.emit_line("m");
        self.indent_level -= 1;
        self.emit_line("});");
        self.emit_line("");
        self.emit_line("fn vox_doc_lookup(name: &str) -> String {");
        self.indent_level += 1;
        self.emit_line("VOX_DOC_REGISTRY.get(name).map(|s| s.to_string()).unwrap_or_default()");
        self.indent_level -= 1;
        self.emit_line("}");
    }

    /// Generate VoxReflect trait and implementations for runtime reflection
    fn emit_reflect_metadata(&mut self) {
        self.emit_line("");
        self.emit_line("// === Vox Reflect: runtime type metadata (signatures only, no implementation) ===");
        self.emit_line("");

        // Emit the trait
        self.emit_line("pub trait VoxReflect {");
        self.indent_level += 1;
        self.emit_line("fn vox_type_name() -> &'static str;");
        self.emit_line("fn vox_fields() -> &'static [&'static str];");
        self.emit_line("fn vox_field_types() -> &'static [(&'static str, &'static str)];");
        self.emit_line("fn vox_methods() -> &'static [&'static str];");
        self.emit_line("fn vox_variants() -> &'static [&'static str];");
        self.emit_line("fn vox_is_struct() -> bool;");
        self.emit_line("fn vox_is_enum() -> bool;");
        self.emit_line("fn vox_is_class() -> bool;");
        self.emit_line("fn vox_is_trait() -> bool;");
        self.indent_level -= 1;
        self.emit_line("}");

        // Emit impl for each type
        let type_names: Vec<String> = self.type_metadata.keys().cloned().collect();
        for type_name in &type_names {
            // Clone the metadata so we don't hold an immutable borrow of `self`
            // while calling `self.emit_line(...)` (which needs `&mut self`).
            let meta = match self.type_metadata.get(type_name) {
                Some(m) => m.clone(),
                None => continue,
            };
            // Skip traits — can't impl a trait for another trait
            if matches!(meta.kind, TypeKind::Trait) {
                continue;
            }
            self.emit_line("");
            self.emit_line(&format!("impl VoxReflect for {} {{", type_name));
            self.indent_level += 1;

            // type_name
            self.emit_line(&format!("fn vox_type_name() -> &'static str {{ \"{}\" }}", meta.name));

            // fields
            let field_strs: Vec<String> = meta.fields.iter()
                .map(|f| format!("\"{}\"", f.name)).collect();
            self.emit_line(&format!("fn vox_fields() -> &'static [&'static str] {{ &[{}] }}", field_strs.join(", ")));

            // field_types
            let ft_strs: Vec<String> = meta.fields.iter()
                .map(|f| format!("(\"{}\", \"{}\")", f.name, f.type_annotation.name()))
                .collect();
            self.emit_line(&format!("fn vox_field_types() -> &'static [(&'static str, &'static str)] {{ &[{}] }}", ft_strs.join(", ")));

            // methods
            let method_strs: Vec<String> = meta.methods.iter()
                .map(|m| format!("\"{}\"", m)).collect();
            self.emit_line(&format!("fn vox_methods() -> &'static [&'static str] {{ &[{}] }}", method_strs.join(", ")));

            // variants
            let variant_strs: Vec<String> = meta.variants.iter()
                .map(|v| format!("\"{}\"", v.name)).collect();
            self.emit_line(&format!("fn vox_variants() -> &'static [&'static str] {{ &[{}] }}", variant_strs.join(", ")));

            // is_struct / is_enum / is_class / is_trait
            let is_struct = matches!(meta.kind, TypeKind::Struct);
            let is_enum = matches!(meta.kind, TypeKind::Enum);
            let is_class = matches!(meta.kind, TypeKind::Class);
            let is_trait = matches!(meta.kind, TypeKind::Trait);
            self.emit_line(&format!("fn vox_is_struct() -> bool {{ {} }}", is_struct));
            self.emit_line(&format!("fn vox_is_enum() -> bool {{ {} }}", is_enum));
            self.emit_line(&format!("fn vox_is_class() -> bool {{ {} }}", is_class));
            self.emit_line(&format!("fn vox_is_trait() -> bool {{ {} }}", is_trait));

            self.indent_level -= 1;
            self.emit_line("}");
        }
    }

    fn extract_type_name_from_args(&self, args: &[Expr]) -> Option<String> {
        match args.first() {
            Some(Expr::Ident { name, .. }) => {
                if self.type_metadata.contains_key(name) {
                    Some(name.clone())
                } else {
                    None
                }
            }
            _ => None,
        }
    }

    fn extract_source(&self, span: &Span) -> String {
        if self.source_code.is_empty() {
            return String::new();
        }
        let lines: Vec<&str> = self.source_code.lines().collect();
        let start_line = span.line.saturating_sub(1);
        let end_line = span.end_line.min(lines.len());
        if start_line >= lines.len() {
            return String::new();
        }
        lines[start_line..end_line].join("\n")
    }

    fn format_signature(&self, meta: &FnMeta) -> String {
        let params: Vec<String> = meta.params.iter()
            .map(|p| {
                if p.name == "self" {
                    "self".to_string()
                } else {
                    let type_str = p.type_annotation.as_ref()
                        .map(|t| t.name())
                        .unwrap_or_else(|| "?".to_string());
                    format!("{}: {}", p.name, type_str)
                }
            })
            .collect();
        let ret_str = meta.return_type.as_ref()
            .map(|t| format!(" -> {}", t.name()))
            .unwrap_or_default();
        format!("def {}({}){}", meta.name, params.join(", "), ret_str)
    }

    fn escape_string(&self, s: &str) -> String {
        s.replace('\\', "\\\\")
         .replace('"', "\\\"")
         .replace('\n', "\\n")
         .replace('\r', "\\r")
         .replace('\t', "\\t")
    }

    fn gen_literal(&self, lit: &LiteralValue) -> String {
        match lit {
            LiteralValue::Int(n) => {
                // Emit `_i64` suffix so Rust can infer the concrete type
                // (avoids "ambiguous numeric type" when calling .abs()/.pow() etc.)
                format!("{}_i64", n)
            }
            LiteralValue::Float(f) => {
                let s = f.to_string();
                // Always emit `_f64` suffix so Rust can infer the concrete type
                // (avoids "ambiguous numeric type" when calling .floor()/.ceil() etc.)
                if s.contains('.') {
                    format!("{}_f64", s)
                } else {
                    format!("{}.0_f64", s)
                }
            }
            LiteralValue::String(s) => format!("\"{}\".to_string()", self.escape_string(s)),
            LiteralValue::Bool(b) => b.to_string(),
            LiteralValue::None => "None".to_string(),
        }
    }

    fn gen_param(&self, p: &FnParam) -> String {
        if p.name == "self" {
            "&self".to_string()
        } else {
            let type_str = p.type_annotation
                .as_ref()
                .map(|t| format!(": {}", self.gen_type(t)))
                .unwrap_or_default();
            format!("{}{}", p.name, type_str)
        }
    }

    /// Generate field type with automatic Box wrapping for self-referential fields
    fn gen_field_type(&self, struct_name: &str, field_name: &str, ty: &Type) -> String {
        // Check if this is a self-referential field
        if let Some(meta) = self.type_metadata.get(struct_name) {
            if meta.self_ref_fields.contains(field_name) {
                let strategy = meta.field_ptrs.get(field_name).unwrap_or(&PtrStrategy::Box);
                let inner_type = self.gen_type_raw(ty);
                return match strategy {
                    PtrStrategy::Box => format!("Option<Box<{}>>", inner_type),
                    PtrStrategy::Arc => format!("Option<Arc<Mutex<{}>>>", inner_type),
                    PtrStrategy::Rc => format!("Option<Rc<RefCell<{}>>>", inner_type),
                    PtrStrategy::Raw => format!("*mut {}", inner_type),
                };
            }
        }
        self.gen_type(ty)
    }

    /// Generate type without Option wrapping (for use inside Box/Arc)
    fn gen_type_raw(&self, ty: &Type) -> String {
        match ty {
            Type::Optional { inner, .. } => self.gen_type(inner),
            _ => self.gen_type(ty),
        }
    }

    fn gen_type(&self, ty: &Type) -> String {
        match ty {
            Type::Named { name, .. } => {
                // Handle dotted ctypes type names: ctypes.c_int, ctypes.c_long, etc.
                if let Some(rest) = name.strip_prefix("ctypes.") {
                    if let Some(rust_type) = self.ctypes_type_to_rust(rest) {
                        return rust_type.to_string();
                    }
                }
                match name.as_str() {
                    "int" => "i64".to_string(),
                    "i32" => "i32".to_string(),
                    "i64" => "i64".to_string(),
                    "f64" => "f64".to_string(),
                    "f32" => "f32".to_string(),
                    "float" => "f64".to_string(),
                    "str" => "String".to_string(),
                    "bool" => "bool".to_string(),
                    "void" => "()".to_string(),
                    other => other.to_string(),
                }
            }
            Type::Optional { inner, .. } => format!("Option<{}>", self.gen_type(inner)),
            Type::List { inner, .. } => format!("Vec<{}>", self.gen_type(inner)),
            Type::Dict { key, value, .. } => format!("HashMap<{}, {}>", self.gen_type(key), self.gen_type(value)),
            Type::Set { inner, .. } => format!("HashSet<{}>", self.gen_type(inner)),
            Type::Generic { base, args, .. } => {
                let args_str = args.iter().map(|a| self.gen_type(a)).collect::<Vec<_>>().join(", ");
                match base.as_str() {
                    "typing.List" => format!("Vec<{}>", args_str),
                    "typing.Dict" => {
                        let parts: Vec<String> = args.iter().map(|a| self.gen_type(a)).collect();
                        if parts.len() >= 2 {
                            format!("HashMap<{}, {}>", parts[0], parts[1])
                        } else {
                            format!("HashMap<{}, {}>", parts[0], parts[0])
                        }
                    }
                    "typing.Set" => format!("HashSet<{}>", args_str),
                    "typing.Optional" => format!("Option<{}>", args_str),
                    "typing.Union" => {
                        format!("std::result::Result<{}, {}>", self.gen_type(&args[0]), self.gen_type(&args[1]))
                    }
                    "typing.Any" => "()".to_string(),
                    "typing.Callable" => "fn()".to_string(),
                    other => format!("{}<{}>", other, args_str),
                }
            }
            Type::Tuple { types, .. } => {
                let types_str = types.iter().map(|t| self.gen_type(t)).collect::<Vec<_>>().join(", ");
                format!("({})", types_str)
            }
            _ => "/* type */".to_string(),
        }
    }

    fn gen_binop(&self, op: &BinaryOperator) -> &'static str {
        match op {
            BinaryOperator::Add => "+",
            BinaryOperator::Sub => "-",
            BinaryOperator::Mul => "*",
            BinaryOperator::Div => "/",
            BinaryOperator::Mod => "%",
            BinaryOperator::Eq => "==",
            BinaryOperator::Ne => "!=",
            BinaryOperator::Lt => "<",
            BinaryOperator::Gt => ">",
            BinaryOperator::Le => "<=",
            BinaryOperator::Ge => ">=",
            BinaryOperator::And => "&&",
            BinaryOperator::Or => "||",
            BinaryOperator::Range => "..",
            BinaryOperator::RangeInclusive => "..=",
            BinaryOperator::Pow => "/* pow */",
            _ => "/* op */",
        }
    }

    fn gen_unop(&self, op: &UnaryOperator) -> &'static str {
        match op {
            UnaryOperator::Neg => "-",
            UnaryOperator::Not => "!",
            _ => "/* unop */",
        }
    }

    fn emit_line(&mut self, line: &str) {
        for _ in 0..self.indent_level {
            self.output.push_str("    ");
        }
        self.output.push_str(line);
        self.output.push('\n');

        // Track source map: rust_line -> (vox_file, vox_line)
        self.rust_line_counter += 1;
        self.source_map.push((
            self.rust_line_counter,
            self.current_vox_file.clone(),
            self.current_vox_line,
        ));
    }

    /// Emit raw text without indentation tracking — for pre-formatted code blocks
    fn emit_raw(&mut self, text: &str) {
        for raw_line in text.lines() {
            for _ in 0..self.indent_level {
                self.output.push_str("    ");
            }
            self.output.push_str(raw_line);
            self.output.push('\n');
            self.rust_line_counter += 1;
            self.source_map.push((
                self.rust_line_counter,
                self.current_vox_file.clone(),
                self.current_vox_line,
            ));
        }
    }

    fn gen_generics_def(&self, generics: &[GenericParam]) -> String {
        if generics.is_empty() {
            return String::new();
        }
        let params: Vec<String> = generics.iter().map(|g| g.name.clone()).collect();
        format!("<{}>", params.join(", "))
    }

    fn gen_pattern(&self, pattern: &Pattern) -> String {
        match pattern {
            Pattern::Ident { name, .. } => {
                if name == "_" {
                    "_".to_string()
                } else if let Some(enum_name) = self.find_enum_for_variant(name) {
                    format!("{}::{}", enum_name, name)
                } else if self.enum_types.contains(name) {
                    format!("{}::{}", name, name)
                } else {
                    name.clone()
                }
            }
            Pattern::Lit { value, .. } => self.gen_literal(value),
            Pattern::Wildcard { .. } => "_".to_string(),
            Pattern::Destructure { patterns, .. } => {
                let parts: Vec<String> = patterns.iter().map(|p| self.gen_pattern(p)).collect();
                format!("({})", parts.join(", "))
            }
            Pattern::Guard { pattern, condition, .. } => {
                format!("{} if {}", self.gen_pattern(pattern), self.gen_expr(condition))
            }
            _ => format!("/* pattern */"),
        }
    }

    fn find_enum_for_variant(&self, variant_name: &str) -> Option<&String> {
        for (enum_name, variants) in &self.enum_variants {
            if variants.iter().any(|v| v == variant_name) {
                return Some(enum_name);
            }
        }
        None
    }

    // ===== Standard library usage scanning (auto-dependency detection) =====

    /// Scan the module for standard library usage that requires external crates.
    /// Detects:
    /// - `re.xxx()` / `re.xxx` usage → auto-adds the `regex` crate
    /// - `time.xxx()` / `datetime.xxx()` calls → sets `needs_time_base`/`needs_chrono`
    ///   and auto-adds the `chrono` crate when date-functions are used.
    fn scan_stdlib_usage(&mut self, module: &Module) {
        let mut needs_regex = false;
        for stmt in &module.statements {
            if self.scan_stmt_for_re(stmt) {
                needs_regex = true;
            }
            self.scan_stmt_for_stdlib(stmt);
        }
        if needs_regex {
            let has_regex = self.transtime.dependencies.iter().any(|(name, _)| name == "regex");
            if !has_regex {
                self.transtime.dependencies.push(("regex".to_string(), "1".to_string()));
            }
        }
        if self.needs_chrono {
            let has_chrono = self.transtime.dependencies.iter()
                .any(|(name, _)| name == "chrono");
            if !has_chrono {
                self.transtime.dependencies.push(("chrono".to_string(), "0.4".to_string()));
            }
        }
    }

    /// Recursively scan a statement for `re` module usage.
    fn scan_stmt_for_re(&self, stmt: &Stmt) -> bool {
        match stmt {
            Stmt::ExprStmt { expr, .. } => self.scan_expr_for_re(expr),
            Stmt::VarDecl { value, .. } => self.scan_expr_for_re(value),
            Stmt::ConstDecl { value, .. } => self.scan_expr_for_re(value),
            Stmt::LazyDecl { value, .. } => self.scan_expr_for_re(value),
            Stmt::AssignStmt { target, value, .. } => {
                self.scan_expr_for_re(target) || self.scan_expr_for_re(value)
            }
            Stmt::ReturnStmt { value, .. } => value.as_ref().map(|e| self.scan_expr_for_re(e)).unwrap_or(false),
            Stmt::FnDef { body, .. } => body.iter().any(|s| self.scan_stmt_for_re(s)),
            Stmt::IfStmt { condition, then_body, elif_chain, else_body, .. } => {
                self.scan_expr_for_re(condition)
                    || then_body.iter().any(|s| self.scan_stmt_for_re(s))
                    || elif_chain.iter().any(|(c, b)| {
                        self.scan_expr_for_re(c) || b.iter().any(|s| self.scan_stmt_for_re(s))
                    })
                    || else_body.as_ref().map(|b| b.iter().any(|s| self.scan_stmt_for_re(s))).unwrap_or(false)
            }
            Stmt::ForLoop { iterable, body, .. } => {
                self.scan_expr_for_re(iterable) || body.iter().any(|s| self.scan_stmt_for_re(s))
            }
            Stmt::WhileLoop { condition, body, .. } => {
                self.scan_expr_for_re(condition) || body.iter().any(|s| self.scan_stmt_for_re(s))
            }
            Stmt::MatchStmt { expr, arms, .. } => {
                self.scan_expr_for_re(expr)
                    || arms.iter().any(|a| {
                        a.guard.as_ref().map(|g| self.scan_expr_for_re(g)).unwrap_or(false)
                            || a.body.iter().any(|s| self.scan_stmt_for_re(s))
                    })
            }
            Stmt::ClassDef { methods, .. } => methods.iter().any(|m| self.scan_stmt_for_re(m)),
            Stmt::ImplBlock { methods, .. } => methods.iter().any(|m| self.scan_stmt_for_re(m)),
            Stmt::ExtendDecl { methods, .. } => methods.iter().any(|m| self.scan_stmt_for_re(m)),
            Stmt::TestStmt { body, .. } => body.iter().any(|s| self.scan_stmt_for_re(s)),
            Stmt::SuiteStmt { body, .. } => body.iter().any(|s| self.scan_stmt_for_re(s)),
            Stmt::DecoratedStmt { stmt, .. } => self.scan_stmt_for_re(stmt),
            _ => false,
        }
    }

    /// Recursively scan an expression for `re` module usage.
    fn scan_expr_for_re(&self, expr: &Expr) -> bool {
        match expr {
            Expr::MethodCall { receiver, args, .. } => {
                if let Expr::Ident { name, .. } = receiver.as_ref() {
                    if name == "re" {
                        return true;
                    }
                }
                self.scan_expr_for_re(receiver) || args.iter().any(|a| self.scan_expr_for_re(a))
            }
            Expr::Attribute { target, .. } => {
                if let Expr::Ident { name, .. } = target.as_ref() {
                    if name == "re" {
                        return true;
                    }
                }
                self.scan_expr_for_re(target)
            }
            Expr::Call { func, args, .. } => {
                self.scan_expr_for_re(func) || args.iter().any(|a| self.scan_expr_for_re(a))
            }
            Expr::BinaryOp { left, right, .. } => {
                self.scan_expr_for_re(left) || self.scan_expr_for_re(right)
            }
            Expr::UnaryOp { operand, .. } => self.scan_expr_for_re(operand),
            Expr::ListLiteral { elements, .. } => elements.iter().any(|e| self.scan_expr_for_re(e)),
            Expr::TupleLiteral { elements, .. } => elements.iter().any(|e| self.scan_expr_for_re(e)),
            Expr::SetLiteral { elements, .. } => elements.iter().any(|e| self.scan_expr_for_re(e)),
            Expr::DictLiteral { entries, .. } => {
                entries.iter().any(|(k, v)| self.scan_expr_for_re(k) || self.scan_expr_for_re(v))
            }
            Expr::Index { target, index, .. } => {
                self.scan_expr_for_re(target) || self.scan_expr_for_re(index)
            }
            Expr::IfExpr { condition, then_expr, else_expr, .. } => {
                self.scan_expr_for_re(condition)
                    || self.scan_expr_for_re(then_expr)
                    || self.scan_expr_for_re(else_expr)
            }
            Expr::Lambda { body, .. } => self.scan_expr_for_re(body),
            _ => false,
        }
    }

    // ===== Standard library: module attribute helpers =====
    // Note: is_std_module and gen_module_attr are defined earlier in this impl block.

    // ===== Standard library: string module =====

    /// Return the Rust string literal for a `string.<constant>` attribute access.
    fn string_constant(&self, name: &str) -> Option<String> {
        let lit = match name {
            "ascii_lowercase" => r#""abcdefghijklmnopqrstuvwxyz".to_string()"#,
            "ascii_uppercase" => r#""ABCDEFGHIJKLMNOPQRSTUVWXYZ".to_string()"#,
            "ascii_letters" => r#""abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ".to_string()"#,
            "digits" => r#""0123456789".to_string()"#,
            "hexdigits" => r#""0123456789abcdefABCDEF".to_string()"#,
            "octdigits" => r#""01234567".to_string()"#,
            "punctuation" => "\"!\\\"#$%&'()*+,-./:;<=>?@[\\\\]^_`{|}~\".to_string()",
            "whitespace" => r#"" \t\n\r\x0b\x0c".to_string()"#,
            _ => return None,
        };
        Some(lit.to_string())
    }

    /// Generate code for `string.xxx(args...)` calls.
    fn gen_stdlib_string_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "split" => {
                if args.len() >= 2 {
                    format!("{}.split(({}).as_str()).map(|s| s.to_string()).collect::<Vec<_>>()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* string.split: needs (s, sep) */".to_string()
                }
            }
            "join" => {
                if args.len() >= 2 {
                    format!("{}.join({})", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* string.join: needs (iterable, sep) */".to_string()
                }
            }
            "find" => {
                if args.len() >= 2 {
                    format!("({}).find(({}).as_str()).map(|i| i as i64).unwrap_or(-1)",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* string.find: needs (s, sub) */".to_string()
                }
            }
            "replace" => {
                if args.len() >= 3 {
                    format!("({}).replace(({}).as_str(), ({}).as_str())",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]), self.gen_expr(&args[2]))
                } else {
                    "/* string.replace: needs (s, old, new) */".to_string()
                }
            }
            "strip" => {
                match args.len() {
                    1 => format!("({}).trim().to_string()", self.gen_expr(&args[0])),
                    2 => format!("({}).trim_matches(|c: char| ({}).contains(c)).to_string()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])),
                    _ => "/* string.strip: needs (s, chars?) */".to_string(),
                }
            }
            "lstrip" => {
                match args.len() {
                    1 => format!("({}).trim_start().to_string()", self.gen_expr(&args[0])),
                    2 => format!("({}).trim_start_matches(|c: char| ({}).contains(c)).to_string()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])),
                    _ => "/* string.lstrip: needs (s, chars?) */".to_string(),
                }
            }
            "rstrip" => {
                match args.len() {
                    1 => format!("({}).trim_end().to_string()", self.gen_expr(&args[0])),
                    2 => format!("({}).trim_end_matches(|c: char| ({}).contains(c)).to_string()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])),
                    _ => "/* string.rstrip: needs (s, chars?) */".to_string(),
                }
            }
            "upper" => {
                if let Some(arg) = args.first() {
                    format!("({}).to_uppercase()", self.gen_expr(arg))
                } else {
                    "/* string.upper: missing arg */".to_string()
                }
            }
            "lower" => {
                if let Some(arg) = args.first() {
                    format!("({}).to_lowercase()", self.gen_expr(arg))
                } else {
                    "/* string.lower: missing arg */".to_string()
                }
            }
            "title" => {
                if let Some(arg) = args.first() {
                    format!("{{ let __s = &({}); let mut __r = String::new(); let mut __prev = ' '; for __c in __s.chars() {{ if __prev.is_whitespace() {{ __r.extend(__c.to_uppercase()); }} else {{ __r.extend(__c.to_lowercase()); }} __prev = __c; }} __r }}", self.gen_expr(arg))
                } else {
                    "/* string.title: missing arg */".to_string()
                }
            }
            "startswith" => {
                if args.len() >= 2 {
                    format!("({}).starts_with(({}).as_str())", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* string.startswith: needs (s, prefix) */".to_string()
                }
            }
            "endswith" => {
                if args.len() >= 2 {
                    format!("({}).ends_with(({}).as_str())", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* string.endswith: needs (s, suffix) */".to_string()
                }
            }
            "contains" => {
                if args.len() >= 2 {
                    format!("({}).contains(({}).as_str())", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* string.contains: needs (s, sub) */".to_string()
                }
            }
            "format" => {
                if args.is_empty() {
                    return "/* string.format: needs (fmt, args...) */".to_string();
                }
                let fmt = self.gen_expr(&args[0]);
                let rest: Vec<String> = args[1..].iter().map(|a| self.gen_expr(a)).collect();
                if rest.is_empty() {
                    fmt
                } else {
                    format!("{{ let mut __r = ({}).clone(); for __a in [{}].iter() {{ __r = __r.replacen(\"{{}}\", &__a.to_string(), 1); }} __r }}",
                        fmt, rest.join(", "))
                }
            }
            "center" => {
                match args.len() {
                    2 => format!("{{ let __s = &({}); let __w = ({}) as usize; let __len = __s.len(); if __len >= __w {{ __s.to_string() }} else {{ let __pad = (__w - __len) / 2; let __extra = (__w - __len) % 2; let __l: String = std::iter::repeat(' ').take(__pad).collect(); let __r: String = std::iter::repeat(' ').take(__pad + __extra).collect(); format!(\"{{}}{{}}{{}}\", __l, __s, __r) }} }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])),
                    3 => format!("{{ let __s = &({}); let __w = ({}) as usize; let __c = ({}).chars().next().unwrap_or(' '); let __len = __s.len(); if __len >= __w {{ __s.to_string() }} else {{ let __pad = (__w - __len) / 2; let __extra = (__w - __len) % 2; let __l: String = std::iter::repeat(__c).take(__pad).collect(); let __r: String = std::iter::repeat(__c).take(__pad + __extra).collect(); format!(\"{{}}{{}}{{}}\", __l, __s, __r) }} }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]), self.gen_expr(&args[2])),
                    _ => "/* string.center: needs (s, width, fillchar?) */".to_string(),
                }
            }
            "ljust" => {
                match args.len() {
                    2 => format!("{{ let __s = &({}); let __w = ({}) as usize; let __len = __s.len(); if __len >= __w {{ __s.to_string() }} else {{ format!(\"{{}}{{}}\", __s, std::iter::repeat(' ').take(__w - __len).collect::<String>()) }} }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])),
                    3 => format!("{{ let __s = &({}); let __w = ({}) as usize; let __c = ({}).chars().next().unwrap_or(' '); let __len = __s.len(); if __len >= __w {{ __s.to_string() }} else {{ format!(\"{{}}{{}}\", __s, std::iter::repeat(__c).take(__w - __len).collect::<String>()) }} }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]), self.gen_expr(&args[2])),
                    _ => "/* string.ljust: needs (s, width, fillchar?) */".to_string(),
                }
            }
            "rjust" => {
                match args.len() {
                    2 => format!("{{ let __s = &({}); let __w = ({}) as usize; let __len = __s.len(); if __len >= __w {{ __s.to_string() }} else {{ format!(\"{{}}{{}}\", std::iter::repeat(' ').take(__w - __len).collect::<String>(), __s) }} }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])),
                    3 => format!("{{ let __s = &({}); let __w = ({}) as usize; let __c = ({}).chars().next().unwrap_or(' '); let __len = __s.len(); if __len >= __w {{ __s.to_string() }} else {{ format!(\"{{}}{{}}\", std::iter::repeat(__c).take(__w - __len).collect::<String>(), __s) }} }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]), self.gen_expr(&args[2])),
                    _ => "/* string.rjust: needs (s, width, fillchar?) */".to_string(),
                }
            }
            "zfill" => {
                if args.len() >= 2 {
                    format!("{{ let __s = &({}); let __w = ({}) as usize; let __len = __s.len(); if __len >= __w {{ __s.to_string() }} else {{ format!(\"0{{}}{{}}\", std::iter::repeat('0').take(__w - __len).collect::<String>(), __s) }} }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* string.zfill: needs (s, width) */".to_string()
                }
            }
            "capwords" => {
                match args.len() {
                    1 => format!("{{ let __s = &({}); __s.split(' ').map(|__w| {{ let mut __c = __w.chars(); match __c.next() {{ Some(__f) => __f.to_uppercase().chain(__c.flat_map(|c| c.to_lowercase())).collect::<String>(), None => String::new() }} }}).collect::<Vec<_>>().join(\" \") }}",
                        self.gen_expr(&args[0])),
                    2 => format!("{{ let __s = &({}); let __sep = &({}); __s.split(__sep).map(|__w| {{ let mut __c = __w.chars(); match __c.next() {{ Some(__f) => __f.to_uppercase().chain(__c.flat_map(|c| c.to_lowercase())).collect::<String>(), None => String::new() }} }}).collect::<Vec<_>>().join(__sep) }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])),
                    _ => "/* string.capwords: needs (s, sep?) */".to_string(),
                }
            }
            _ => format!("/* string.{}: not implemented */", method),
        }
    }

    // ===== Standard library: re module (regex) =====

    /// Generate code for `re.xxx(args...)` calls.
    fn gen_stdlib_re_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "compile" => {
                if let Some(arg) = args.first() {
                    format!("regex::Regex::new(&({})).unwrap()", self.gen_expr(arg))
                } else {
                    "/* re.compile: needs (pattern) */".to_string()
                }
            }
            "match" => {
                if args.len() >= 2 {
                    format!("regex::Regex::new(&({})).unwrap().is_match(&({}))",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* re.match: needs (pattern, string) */".to_string()
                }
            }
            "search" => {
                if args.len() >= 2 {
                    format!("regex::Regex::new(&({})).unwrap().is_match(&({}))",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* re.search: needs (pattern, string) */".to_string()
                }
            }
            "findall" => {
                if args.len() >= 2 {
                    format!("regex::Regex::new(&({})).unwrap().find_iter(&({})).map(|m| m.as_str().to_string()).collect::<Vec<_>>()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* re.findall: needs (pattern, string) */".to_string()
                }
            }
            "sub" => {
                if args.len() >= 3 {
                    format!("regex::Regex::new(&({})).unwrap().replace_all(&({}), &({})).to_string()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[2]), self.gen_expr(&args[1]))
                } else {
                    "/* re.sub: needs (pattern, repl, string) */".to_string()
                }
            }
            "split" => {
                if args.len() >= 2 {
                    format!("regex::Regex::new(&({})).unwrap().split(&({})).map(|s| s.to_string()).collect::<Vec<_>>()",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* re.split: needs (pattern, string) */".to_string()
                }
            }
            "escape" => {
                if let Some(arg) = args.first() {
                    format!("regex::escape(&({}))", self.gen_expr(arg))
                } else {
                    "/* re.escape: needs (string) */".to_string()
                }
            }
            _ => format!("/* re.{}: not implemented */", method),
        }
    }

    // ===== Standard library: funcs module (functional utilities) =====

    /// Generate code for `funcs.xxx(args...)` calls.
    fn gen_stdlib_funcs_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "identity" => {
                if let Some(arg) = args.first() {
                    self.gen_expr(arg)
                } else {
                    "/* funcs.identity: missing arg */".to_string()
                }
            }
            "compose" => {
                // funcs.compose(f, g) → move |x| f(g(x))
                if args.len() >= 2 {
                    format!("move |__x| ({})(({})(__x))", self.gen_expr(&args[0]), self.gen_expr(&args[1]))
                } else {
                    "/* funcs.compose: needs (f, g) */".to_string()
                }
            }
            "partial" => {
                // funcs.partial(func, a, b, ...) → move |x| func(a, b, ..., x)
                if args.is_empty() {
                    return "/* funcs.partial: needs (func, args...) */".to_string();
                }
                let func = self.gen_expr(&args[0]);
                let bound: Vec<String> = args[1..].iter().map(|a| self.gen_expr(a)).collect();
                if bound.is_empty() {
                    format!("move |__x| ({})({})", func, "__x")
                } else {
                    format!("move |__x| ({})({}, __x)", func, bound.join(", "))
                }
            }
            "reduce" => {
                // funcs.reduce(func, iterable, initial?) → loop accumulation
                match args.len() {
                    2 => format!("{{ let mut __acc: i64 = 0; for __item in &({}) {{ __acc = ({})(__acc, __item); }} __acc }}",
                        self.gen_expr(&args[1]), self.gen_expr(&args[0])),
                    3 => format!("{{ let mut __acc = ({}); for __item in &({}) {{ __acc = ({})(__acc, __item); }} __acc }}",
                        self.gen_expr(&args[2]), self.gen_expr(&args[1]), self.gen_expr(&args[0])),
                    _ => "/* funcs.reduce: needs (func, iterable, initial?) */".to_string(),
                }
            }
            "constantly" => {
                // funcs.constantly(x) → move |_| x.clone()
                if let Some(arg) = args.first() {
                    format!("move |__x| {{ let _ = __x; ({}).clone() }}", self.gen_expr(arg))
                } else {
                    "/* funcs.constantly: missing arg */".to_string()
                }
            }
            "memoize" => {
                // funcs.memoize(func) → HashMap-backed memoization (i64 -> i64 simplified)
                if let Some(arg) = args.first() {
                    format!("{{ let __cache = std::cell::RefCell::new(std::collections::HashMap::<i64, i64>::new()); let __f = ({}); move |__x: i64| {{ {{ let mut __c = __cache.borrow_mut(); if let Some(__v) = __c.get(&__x) {{ return *__v; }} }} let __r = __f(__x); __cache.borrow_mut().insert(__x, __r); __r }} }}", self.gen_expr(arg))
                } else {
                    "/* funcs.memoize: missing arg */".to_string()
                }
            }
            "curry" => {
                // funcs.curry(func) → move |x| move |y| func(x, y)
                if let Some(arg) = args.first() {
                    format!("move |__x| move |__y| ({})(__x, __y)", self.gen_expr(arg))
                } else {
                    "/* funcs.curry: missing arg */".to_string()
                }
            }
            "uncurry" => {
                // funcs.uncurry(func) → move |x, y| func(x)(y)
                if let Some(arg) = args.first() {
                    format!("move |__x, __y| ({})(__x)(__y)", self.gen_expr(arg))
                } else {
                    "/* funcs.uncurry: missing arg */".to_string()
                }
            }
            _ => format!("/* funcs.{}: not implemented */", method),
        }
    }

    // ===== Standard library: gc, collection, itors modules =====

    /// Generate code for `gc.<method>(args)`, `collection.<method>(args)`,
    /// and `itors.<method>(args)` calls.
    ///
    /// These modules provide garbage collection control, container datatypes,
    /// and iterator tools modeled after Python's `gc`, `collections`, and `itertools`.
    fn gen_stdlib_call(&self, module: &str, method: &str, args: &[Expr]) -> String {
        match module {
            "gc" => self.gen_gc_call(method, args),
            "collection" => self.gen_collection_call(method, args),
            "itors" => self.gen_itors_call(method, args),
            _ => format!("/* {}.{}: unknown module */", module, method),
        }
    }

    /// Generate code for `gc.<method>(args)`.
    ///
    /// Rust uses ownership-based memory management instead of a GC,
    /// so these are mostly no-ops returning sentinel values.
    fn gen_gc_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "collect" => {
                // gc.collect() -> 0 (no GC in Rust; return 0 collected objects)
                "0".to_string()
            }
            "disable" => {
                // gc.disable() -> no-op
                "()".to_string()
            }
            "enable" => {
                // gc.enable() -> no-op
                "()".to_string()
            }
            "get_count" => {
                // gc.get_count() -> 0
                "0".to_string()
            }
            "get_stats" => {
                // gc.get_stats() -> (0, 0, 0) tuple of collection counts
                "(0, 0, 0)".to_string()
            }
            "set_debug" => {
                // gc.set_debug(flags) -> no-op
                "()".to_string()
            }
            "get_referrers" => {
                // gc.get_referrers(obj) -> vec![] (Rust has no referrer tracking)
                if args.first().is_some() {
                    "Vec::<()>::new()".to_string()
                } else {
                    "/* gc.get_referrers: missing arg */ Vec::<()>::new()".to_string()
                }
            }
            "get_referents" => {
                // gc.get_referents(obj) -> vec![] (Rust has no referent tracking)
                if args.first().is_some() {
                    "Vec::<()>::new()".to_string()
                } else {
                    "/* gc.get_referents: missing arg */ Vec::<()>::new()".to_string()
                }
            }
            _ => format!("/* gc.{}: not implemented */", method),
        }
    }

    /// Generate code for `collection.<method>(args)`.
    ///
    /// Provides container datatypes like Counter, defaultdict, deque, etc.
    fn gen_collection_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            "counter" => {
                // collection.counter(iterable) -> HashMap counting items
                if let Some(arg) = args.first() {
                    format!(
                        "{{ let __it = {}; let mut __m: std::collections::HashMap<i64, i64> = std::collections::HashMap::new(); for __x in __it {{ *(__m.entry(__x).or_insert(0)) += 1; }} __m }}",
                        self.gen_expr(arg)
                    )
                } else {
                    "/* collection.counter: missing iterable */ std::collections::HashMap::new()".to_string()
                }
            }
            "defaultdict" => {
                // collection.defaultdict(default_factory) -> HashMap
                "std::collections::HashMap::<String, String>::new()".to_string()
            }
            "deque" => {
                // collection.deque(iterable) -> VecDeque
                if let Some(arg) = args.first() {
                    format!(
                        "{{ let __it = {}; let mut __d = std::collections::VecDeque::new(); for __x in __it {{ __d.push_back(__x); }} __d }}",
                        self.gen_expr(arg)
                    )
                } else {
                    "/* collection.deque: missing iterable */ std::collections::VecDeque::new()".to_string()
                }
            }
            "namedtuple" => {
                // collection.namedtuple(name, fields) -> tuple placeholder
                if args.len() >= 2 {
                    format!(
                        "/* collection.namedtuple({}, {}): generated as tuple */ (0,)",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])
                    )
                } else {
                    "/* collection.namedtuple: needs (name, fields) */ (0,)".to_string()
                }
            }
            "OrderedDict" => {
                // collection.OrderedDict() -> Vec of (key, value) tuples preserving order
                "Vec::<(i64, i64)>::new()".to_string()
            }
            "ChainMap" => {
                // collection.ChainMap(*maps) -> Vec of HashMaps
                "Vec::<std::collections::HashMap<i64, i64>>::new()".to_string()
            }
            _ => format!("/* collection.{}: not implemented */", method),
        }
    }

    /// Generate code for `itors.<method>(args)`.
    ///
    /// Provides iterator tools like count, cycle, chain, takewhile, etc.
    /// Returns Vecs collecting the iterator results for simplicity.
    fn gen_itors_call(&self, method: &str, args: &[Expr]) -> String {
        match method {
            // ===== Infinite iterators =====
            "count" => {
                // itors.count(start, step) -> Vec of count (bounded for safety)
                let start = args.first().map(|a| self.gen_expr(a)).unwrap_or_else(|| "0".to_string());
                let step = args.get(1).map(|a| self.gen_expr(a)).unwrap_or_else(|| "1".to_string());
                format!(
                    "{{ let mut __v: Vec<i64> = Vec::new(); let mut __n: i64 = {}; let __s: i64 = {}; for _ in 0..10 {{ __v.push(__n); __n += __s; }} __v }}",
                    start, step
                )
            }
            "cycle" => {
                // itors.cycle(iterable) -> Vec (one cycle; full cycle is infinite)
                if let Some(arg) = args.first() {
                    format!(
                        "{{ let __it = {}.clone(); __it }}",
                        self.gen_expr(arg)
                    )
                } else {
                    "/* itors.cycle: missing iterable */ Vec::<i64>::new()".to_string()
                }
            }
            "repeat" => {
                // itors.repeat(elem, times) -> Vec of repeated elem
                if args.len() >= 2 {
                    format!(
                        "{{ let __e = {}; let __n: usize = ({}) as usize; vec![__e; __n] }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])
                    )
                } else if args.len() == 1 {
                    // No times specified; repeat once
                    format!(
                        "{{ let __e = {}; vec![__e; 1] }}",
                        self.gen_expr(&args[0])
                    )
                } else {
                    "/* itors.repeat: missing elem */ Vec::<i64>::new()".to_string()
                }
            }
            // ===== Iterator combination =====
            "chain" => {
                // itors.chain(*iterables) -> Vec chaining all iterables
                if let Some(arg) = args.first() {
                    format!(
                        "{{ let __iters = {}; let mut __v: Vec<i64> = Vec::new(); for __it in __iters {{ for __x in __it {{ __v.push(__x); }} }} __v }}",
                        self.gen_expr(arg)
                    )
                } else {
                    "/* itors.chain: missing iterables */ Vec::<i64>::new()".to_string()
                }
            }
            "islice" => {
                // itors.islice(iterable, start, stop, step) -> Vec slice
                if args.len() >= 3 {
                    let step_expr = args.get(3).map(|a| self.gen_expr(a)).unwrap_or_else(|| "1".to_string());
                    format!(
                        "{{ let __it: Vec<i64> = ({}).into_iter().collect(); let __start: usize = ({}) as usize; let __stop: usize = ({}) as usize; let __step: usize = ({}) as usize; let mut __v: Vec<i64> = Vec::new(); let __end = __stop.min(__it.len()); let mut __i = __start; while __i < __end {{ __v.push(__it[__i].clone()); __i += __step; }} __v }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1]), self.gen_expr(&args[2]), step_expr
                    )
                } else {
                    "/* itors.islice: needs (iterable, start, stop) */ Vec::<i64>::new()".to_string()
                }
            }
            // ===== Filtering iterators =====
            "takewhile" => {
                // itors.takewhile(pred, iterable) -> Vec taking while pred is true
                if args.len() >= 2 {
                    format!(
                        "{{ let __pred = {}; let __it = {}; let mut __v: Vec<i64> = Vec::new(); for __x in __it {{ if __pred(__x) {{ __v.push(__x); }} else {{ break; }} }} __v }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])
                    )
                } else {
                    "/* itors.takewhile: needs (pred, iterable) */ Vec::<i64>::new()".to_string()
                }
            }
            "dropwhile" => {
                // itors.dropwhile(pred, iterable) -> Vec dropping while pred is true
                if args.len() >= 2 {
                    format!(
                        "{{ let __pred = {}; let __it = {}; let mut __v: Vec<i64> = Vec::new(); let mut __dropping = true; for __x in __it {{ if __dropping && __pred(__x) {{ continue; }} else {{ __dropping = false; __v.push(__x); }} }} __v }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])
                    )
                } else {
                    "/* itors.dropwhile: needs (pred, iterable) */ Vec::<i64>::new()".to_string()
                }
            }
            // ===== Mapping iterators =====
            "starmap" => {
                // itors.starmap(func, iterable) -> Vec applying func to each tuple
                if args.len() >= 2 {
                    format!(
                        "{{ let __f = {}; let __it = {}; let mut __v: Vec<i64> = Vec::new(); for __x in __it {{ __v.push(__f(__x)); }} __v }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])
                    )
                } else {
                    "/* itors.starmap: needs (func, iterable) */ Vec::<i64>::new()".to_string()
                }
            }
            "accumulate" => {
                // itors.accumulate(iterable, func) -> Vec of running totals
                if args.len() >= 2 {
                    format!(
                        "{{ let __it = {}; let __f = {}; let mut __v: Vec<i64> = Vec::new(); let mut __acc: Option<i64> = None; for __x in __it {{ __acc = Some(match __acc {{ Some(__a) => __f(__a, __x), None => __x, }}); __v.push(__acc.unwrap()); }} __v }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])
                    )
                } else if args.len() == 1 {
                    // Default: sum accumulation
                    format!(
                        "{{ let __it = {}; let mut __v: Vec<i64> = Vec::new(); let mut __acc: i64 = 0; for __x in __it {{ __acc += __x; __v.push(__acc); }} __v }}",
                        self.gen_expr(&args[0])
                    )
                } else {
                    "/* itors.accumulate: missing iterable */ Vec::<i64>::new()".to_string()
                }
            }
            // ===== Grouping iterators =====
            "groupby" => {
                // itors.groupby(iterable, key) -> Vec of (key, Vec) groups
                if args.len() >= 2 {
                    format!(
                        "{{ let __it: Vec<i64> = ({}).into_iter().collect(); let __key = {}; let mut __v: Vec<(i64, Vec<i64>)> = Vec::new(); let mut __cur: Option<(i64, Vec<i64>)> = None; for __x in __it {{ let __k = __key(__x); match &mut __cur {{ Some(g) if g.0 == __k => {{ g.1.push(__x); }} _ => {{ if let Some(g) = __cur.take() {{ __v.push(g); }} __cur = Some((__k, vec![__x])); }} }} }} if let Some(g) = __cur.take() {{ __v.push(g); }} __v }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])
                    )
                } else {
                    "/* itors.groupby: needs (key, iterable) */ Vec::<(i64, Vec<i64>)>::new()".to_string()
                }
            }
            // ===== Combinatorial iterators =====
            "combinations" => {
                // itors.combinations(iterable, r) -> Vec of combinations
                if args.len() >= 2 {
                    format!(
                        "{{ let __it: Vec<i64> = ({}).into_iter().collect(); let __r: usize = ({}) as usize; let mut __v: Vec<Vec<i64>> = Vec::new(); if __r <= __it.len() {{ let mut __idx: Vec<usize> = (0..__r).collect(); loop {{ __v.push(__idx.iter().map(|&i| __it[i].clone()).collect()); let mut __i = __r; while __i > 0 {{ __i -= 1; __idx[__i] += 1; if __idx[__i] <= __it.len() - __r + __i {{ break; }} }} let mut __reset = false; for __j in __i+1..__r {{ __idx[__j] = __idx[__j-1] + 1; if __idx[__j] >= __it.len() {{ __reset = true; break; }} }} if __i == 0 && __idx[0] > __it.len() - __r {{ break; }} }} }} __v }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])
                    )
                } else {
                    "/* itors.combinations: needs (iterable, r) */ Vec::<Vec<i64>>::new()".to_string()
                }
            }
            "permutations" => {
                // itors.permutations(iterable, r) -> Vec of permutations
                if args.len() >= 2 {
                    format!(
                        "{{ let __it: Vec<i64> = ({}).into_iter().collect(); let __r: usize = ({}) as usize; let mut __v: Vec<Vec<i64>> = Vec::new(); if __r <= __it.len() {{ let __n = __it.len(); let mut __idx: Vec<usize> = (0..__n).collect(); let mut __used = vec![false; __n]; let mut __cur: Vec<usize> = Vec::new(); fn __gen(__idx: &mut Vec<usize>, __used: &mut Vec<bool>, __cur: &mut Vec<usize>, __r: usize, __n: usize, __it: &Vec<i64>, __v: &mut Vec<Vec<i64>>) {{ if __cur.len() == __r {{ __v.push(__cur.iter().map(|&i| __it[i].clone()).collect()); return; }} for __i in 0..__n {{ if !__used[__i] {{ __used[__i] = true; __cur.push(__i); __gen(__idx, __used, __cur, __r, __n, __it, __v); __cur.pop(); __used[__i] = false; }} }} }} __gen(&mut __idx, &mut __used, &mut __cur, __r, __n, &__it, &mut __v); }} __v }}",
                        self.gen_expr(&args[0]), self.gen_expr(&args[1])
                    )
                } else {
                    "/* itors.permutations: needs (iterable, r) */ Vec::<Vec<i64>>::new()".to_string()
                }
            }
            "product" => {
                // itors.product(*iterables) -> Vec of cartesian product tuples
                if let Some(arg) = args.first() {
                    format!(
                        "{{ let __iters: Vec<Vec<i64>> = ({}).into_iter().map(|i| i.into_iter().collect()).collect(); let mut __v: Vec<Vec<i64>> = vec![vec![]]; for __it in __iters {{ let mut __next: Vec<Vec<i64>> = Vec::new(); for __p in &__v {{ for __x in &__it {{ let mut __np = __p.clone(); __np.push(__x.clone()); __next.push(__np); }} }} __v = __next; }} __v }}",
                        self.gen_expr(arg)
                    )
                } else {
                    "/* itors.product: missing iterables */ Vec::<Vec<i64>>::new()".to_string()
                }
            }
            _ => format!("/* itors.{}: not implemented */", method),
        }
    }
}

impl Default for RustCodegen {
    fn default() -> Self {
        Self::new()
    }
}
