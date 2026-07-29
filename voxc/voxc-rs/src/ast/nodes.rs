use serde::{Deserialize, Serialize};

/// Source location span
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Span {
    pub file: String,
    pub line: usize,
    pub col: usize,
    pub end_line: usize,
    pub end_col: usize,
}

impl Span {
    pub fn new(file: &str, line: usize, col: usize, end_line: usize, end_col: usize) -> Self {
        Span {
            file: file.to_string(),
            line,
            col,
            end_line,
            end_col,
        }
    }

    pub fn unknown() -> Self {
        Span {
            file: "<unknown>".to_string(),
            line: 0,
            col: 0,
            end_line: 0,
            end_col: 0,
        }
    }
}

/// Top-level module
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Module {
    pub name: String,
    pub statements: Vec<Stmt>,
    pub span: Span,
}

/// Statement node
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "node")]
pub enum Stmt {
    VarDecl {
        span: Span,
        mutable: bool,
        name: String,
        type_annotation: Option<Type>,
        value: Box<Expr>,
    },
    ConstDecl {
        span: Span,
        name: String,
        type_annotation: Option<Type>,
        value: Box<Expr>,
    },
    LazyDecl {
        span: Span,
        name: String,
        type_annotation: Option<Type>,
        value: Box<Expr>,
    },
    FnDef {
        span: Span,
        name: String,
        generics: Vec<GenericParam>,
        params: Vec<FnParam>,
        return_type: Option<Type>,
        raises: Option<Type>,
        where_clauses: Vec<WhereClause>,
        body: Vec<Stmt>,
        #[serde(default)]
        doc: Option<String>,
    },
    ClassDef {
        span: Span,
        name: String,
        parent: Option<String>,
        fields: Vec<ClassField>,
        methods: Vec<Stmt>,
        #[serde(default)]
        doc: Option<String>,
    },
    StructDef {
        span: Span,
        name: String,
        generics: Vec<GenericParam>,
        fields: Vec<StructField>,
        #[serde(default)]
        doc: Option<String>,
    },
    EnumDef {
        span: Span,
        name: String,
        generics: Vec<GenericParam>,
        variants: Vec<EnumVariant>,
        #[serde(default)]
        doc: Option<String>,
    },
    TraitDef {
        span: Span,
        name: String,
        methods: Vec<TraitMethod>,
        #[serde(default)]
        doc: Option<String>,
    },
    ImplBlock {
        span: Span,
        trait_name: Option<String>,
        type_name: String,
        methods: Vec<Stmt>,
    },
    ExprStmt {
        span: Span,
        expr: Box<Expr>,
    },
    ReturnStmt {
        span: Span,
        value: Option<Box<Expr>>,
    },
    IfStmt {
        span: Span,
        condition: Box<Expr>,
        then_body: Vec<Stmt>,
        elif_chain: Vec<(Expr, Vec<Stmt>)>,
        else_body: Option<Vec<Stmt>>,
    },
    MatchStmt {
        span: Span,
        expr: Box<Expr>,
        arms: Vec<MatchArm>,
    },
    ForLoop {
        span: Span,
        var: String,
        iterable: Box<Expr>,
        guard: Option<Box<Expr>>,
        body: Vec<Stmt>,
        else_body: Option<Vec<Stmt>>,
    },
    WhileLoop {
        span: Span,
        condition: Box<Expr>,
        body: Vec<Stmt>,
        else_body: Option<Vec<Stmt>>,
    },
    LoopStmt {
        span: Span,
        body: Vec<Stmt>,
    },
    TryBlock {
        span: Span,
        try_body: Vec<Stmt>,
        catch_clauses: Vec<CatchClause>,
        else_body: Option<Vec<Stmt>>,
        finally_body: Option<Vec<Stmt>>,
    },
    RaiseStmt {
        span: Span,
        expr: Box<Expr>,
    },
    DeferStmt {
        span: Span,
        expr: Box<Expr>,
    },
    BreakStmt {
        span: Span,
        label: Option<String>,
        value: Option<Box<Expr>>,
    },
    ContinueStmt {
        span: Span,
        label: Option<String>,
    },
    GuardStmt {
        span: Span,
        pattern: Pattern,
        expr: Box<Expr>,
        else_body: Vec<Stmt>,
    },
    ImportStmt {
        span: Span,
        module: Vec<String>,
        items: Option<Vec<String>>,
        alias: Option<String>,
    },
    FromImport {
        span: Span,
        module: Vec<String>,
        items: Vec<String>,
    },
    DefineDecl {
        span: Span,
        name: String,
        generics: Vec<GenericParam>,
        constraints: DefineConstraints,
    },
    EventDecl {
        span: Span,
        name: String,
        generics: Vec<GenericParam>,
        params: Vec<FnParam>,
    },
    TemplateDecl {
        span: Span,
        name: String,
        generics: Vec<GenericParam>,
        params: Vec<FnParam>,
        body: Vec<Stmt>,
    },
    OperatorDecl {
        span: Span,
        op_type: OperatorType,
        symbol: String,
        name: String,
        generics: Vec<GenericParam>,
        params: Vec<(String, Type)>,
        return_type: Type,
        where_clauses: Vec<WhereClause>,
    },
    DecoratedStmt {
        span: Span,
        decorators: Vec<String>,
        stmt: Box<Stmt>,
    },
    AssignStmt {
        span: Span,
        target: Box<Expr>,
        value: Box<Expr>,
    },
    WhenStmt {
        span: Span,
        expr: Box<Expr>,
        branches: Vec<WhenBranch>,
        else_body: Vec<Stmt>,
    },
    TestStmt {
        span: Span,
        name: String,
        body: Vec<Stmt>,
    },
    SuiteStmt {
        span: Span,
        name: String,
        body: Vec<Stmt>,
    },
    ExtendDecl {
        span: Span,
        target: String,
        for_type: String,
        generics: Vec<GenericParam>,
        methods: Vec<Stmt>,
    },
    ComptimeBlock {
        span: Span,
        body: Vec<Stmt>,
    },
    TranstimeBlock {
        span: Span,
        body: Vec<Stmt>,
    },
    IgnoreStmt {
        span: Span,
        target: String,
        name: String,
        body: Vec<Stmt>,
    },
    ExcludeStmt {
        span: Span,
        module: Vec<String>,
        items: Vec<String>,
    },
}

/// Expression node
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "node")]
pub enum Expr {
    Literal {
        span: Span,
        value: LiteralValue,
    },
    Ident {
        span: Span,
        name: String,
    },
    BinaryOp {
        span: Span,
        left: Box<Expr>,
        op: BinaryOperator,
        right: Box<Expr>,
    },
    UnaryOp {
        span: Span,
        op: UnaryOperator,
        operand: Box<Expr>,
    },
    Call {
        span: Span,
        func: Box<Expr>,
        args: Vec<Expr>,
    },
    MethodCall {
        span: Span,
        receiver: Box<Expr>,
        method: String,
        args: Vec<Expr>,
    },
    IfExpr {
        span: Span,
        condition: Box<Expr>,
        then_expr: Box<Expr>,
        else_expr: Box<Expr>,
    },
    Lambda {
        span: Span,
        params: Vec<String>,
        return_type: Option<Type>,
        body: Box<Expr>,
    },
    ListLiteral {
        span: Span,
        elements: Vec<Expr>,
    },
    DictLiteral {
        span: Span,
        entries: Vec<(Expr, Expr)>,
    },
    SetLiteral {
        span: Span,
        elements: Vec<Expr>,
    },
    TupleLiteral {
        span: Span,
        elements: Vec<Expr>,
    },
    Comprehension {
        span: Span,
        kind: ComprehensionKind,
        expr: Box<Expr>,
        bindings: Vec<CompBinding>,
        condition: Option<Box<Expr>>,
    },
    Index {
        span: Span,
        target: Box<Expr>,
        index: Box<Expr>,
    },
    Slice {
        span: Span,
        target: Box<Expr>,
        start: Option<Box<Expr>>,
        end: Option<Box<Expr>>,
        step: Option<Box<Expr>>,
    },
    Attribute {
        span: Span,
        target: Box<Expr>,
        name: String,
    },
    SafeNav {
        span: Span,
        target: Box<Expr>,
        field: String,
    },
    NullCoalesce {
        span: Span,
        left: Box<Expr>,
        right: Box<Expr>,
    },
    Placeholder(Placeholder),
    TypeCast {
        span: Span,
        expr: Box<Expr>,
        target_type: Type,
    },
    Await {
        span: Span,
        expr: Box<Expr>,
    },
    Yield {
        span: Span,
        value: Option<Box<Expr>>,
    },
    MacroExpr {
        span: Span,
        name: String,
        args: Vec<Expr>,
    },
    TemplateInvoke {
        span: Span,
        name: String,
        args: Vec<Expr>,
    },
    EventFire {
        span: Span,
        name: String,
        args: Vec<Expr>,
    },
    Comptime {
        span: Span,
        body: Vec<Stmt>,
    },
}

/// Placeholder expression (`_`)
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Placeholder {
    pub span: Span,
    pub index: usize,
}

/// Literal value
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", content = "value")]
pub enum LiteralValue {
    Int(i64),
    Float(f64),
    String(String),
    Bool(bool),
    None,
}

/// Binary operator
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum BinaryOperator {
    Add,
    Sub,
    Mul,
    Div,
    Mod,
    Pow,
    Eq,
    Ne,
    Lt,
    Gt,
    Le,
    Ge,
    And,
    Or,
    Range,
    RangeInclusive,
    In,
    NotIn,
    Custom(String),
    CustomNthfix(String, Vec<String>),
}

/// Unary operator
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum UnaryOperator {
    Neg,
    Not,
    Custom(String),
}

/// Type node
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "node")]
pub enum Type {
    Named {
        span: Span,
        name: String,
    },
    Generic {
        span: Span,
        base: String,
        args: Vec<Type>,
    },
    Optional {
        span: Span,
        inner: Box<Type>,
    },
    FnType {
        span: Span,
        params: Vec<Type>,
        return_type: Box<Type>,
    },
    Tuple {
        span: Span,
        types: Vec<Type>,
    },
    List {
        span: Span,
        inner: Box<Type>,
    },
    Dict {
        span: Span,
        key: Box<Type>,
        value: Box<Type>,
    },
    Set {
        span: Span,
        inner: Box<Type>,
    },
    DefineRef {
        span: Span,
        name: String,
    },
}

impl Type {
    pub fn name(&self) -> String {
        match self {
            Type::Named { name, .. } => name.clone(),
            Type::Generic { base, args, .. } => {
                let args_str: Vec<String> = args.iter().map(|a| a.name()).collect();
                format!("{}<{}>", base, args_str.join(", "))
            }
            Type::Optional { inner, .. } => format!("{}?", inner.name()),
            Type::FnType { params, return_type, .. } => {
                let params_str: Vec<String> = params.iter().map(|p| p.name()).collect();
                format!("fn({}) -> {}", params_str.join(", "), return_type.name())
            }
            Type::Tuple { types, .. } => {
                let types_str: Vec<String> = types.iter().map(|t| t.name()).collect();
                format!("({})", types_str.join(", "))
            }
            Type::List { inner, .. } => format!("[{}]", inner.name()),
            Type::Dict { key, value, .. } => format!("{{{}: {}}}", key.name(), value.name()),
            Type::Set { inner, .. } => format!("{{{}}}", inner.name()),
            Type::DefineRef { name, .. } => name.clone(),
        }
    }
}

/// Pattern node
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "node")]
pub enum Pattern {
    Ident {
        span: Span,
        name: String,
    },
    Lit {
        span: Span,
        value: LiteralValue,
    },
    Destructure {
        span: Span,
        patterns: Vec<Pattern>,
    },
    NamedDestructure {
        span: Span,
        entries: Vec<(String, Pattern)>,
    },
    Wildcard {
        span: Span,
    },
    Or {
        span: Span,
        left: Box<Pattern>,
        right: Box<Pattern>,
    },
    Guard {
        span: Span,
        pattern: Box<Pattern>,
        condition: Box<Expr>,
    },
}

/// Function parameter
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FnParam {
    pub name: String,
    pub type_annotation: Option<Type>,
    pub default: Option<Expr>,
    pub variadic: bool,
}

/// Generic parameter
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GenericParam {
    pub name: String,
    pub bounds: Vec<Type>,
}

/// Where clause
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WhereClause {
    pub name: String,
    pub bounds: Vec<Type>,
}

/// Class field
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ClassField {
    pub name: String,
    pub type_annotation: Option<Type>,
    pub default: Option<Expr>,
    pub mutable: bool,
}

/// Struct field
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct StructField {
    pub name: String,
    pub type_annotation: Type,
}

/// Enum variant
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EnumVariant {
    pub name: String,
    pub data: Option<Type>,
}

/// Trait method declaration
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TraitMethod {
    pub name: String,
    pub params: Vec<FnParam>,
    pub return_type: Option<Type>,
    pub default_body: Option<Vec<Stmt>>,
}

/// Match arm
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MatchArm {
    pub pattern: Pattern,
    pub guard: Option<Expr>,
    pub body: Vec<Stmt>,
}

/// Catch clause
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CatchClause {
    pub pattern: Option<Pattern>,
    pub body: Vec<Stmt>,
}

/// Define constraints
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DefineConstraints {
    pub props: Vec<(String, Type)>,
    pub statics: Vec<(String, Type)>,
    pub typemethods: Vec<(String, Type)>,
    pub instancemethods: Vec<(String, Type)>,
    pub check: Option<Vec<Stmt>>,
}

/// Operator type for *fix declarations
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum OperatorType {
    Prefix,
    Infix,
    Suffix,
    Nthfix,
    Pairfix,
}

/// Comprehension kind
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ComprehensionKind {
    List,
    Set,
    Dict,
}

/// Comprehension binding
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CompBinding {
    pub var: String,
    pub iterable: Box<Expr>,
}

/// When branch
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WhenBranch {
    pub condition: Expr,
    pub action: WhenAction,
}

/// When action
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum WhenAction {
    ThenExpr(Expr),
    ThenBreak,
    ThenContinue,
    ThenReturn(Option<Box<Expr>>),
}