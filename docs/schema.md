# Warehouse 3D: data schema and how it extends Odoo Inventory

Three diagrams:

1. **ER diagram**: the Odoo Inventory (`stock`) tables we touch, plus our two new tables.
2. **Class diagram**: which Odoo models we extend (`_inherit`) and which we add (`_name`).
3. **Flow diagram**: how data moves between the editor, the models, Inventory and the 3D view.

Model names use `_` instead of `.` because Mermaid entity names cannot contain dots
(`stock_location` = `stock.location`). Fields starting with `wh3d_` are added by this module.

---

## 1. ER diagram: Odoo Inventory + our additions

```mermaid
erDiagram
    %% ---------- Odoo Inventory (standard) ----------
    stock_warehouse {
        int id PK
        char name
        char code "e.g. WHV, TW"
        m2o lot_stock_id FK "WH/Stock"
        float wh3d_length "NEW building size along X (m)"
        float wh3d_width "NEW building size along Y (m)"
        float wh3d_height "NEW clear height (m)"
    }
    stock_location {
        int id PK
        char name
        char complete_name "WH/Stock/PR/P05/P05-03/P05-03-2/P05-03-2-A"
        m2o location_id FK "parent location"
        selection usage "internal / view / supplier ..."
        m2o warehouse_id FK
        m2o storage_category_id FK
        m2o wh3d_rack_row_id FK "NEW rack row that generated it"
        selection wh3d_node "NEW row / bay / level / slot"
        int wh3d_bay "NEW"
        int wh3d_level "NEW"
        int wh3d_position "NEW 1=A, 2=B ..."
    }
    stock_quant {
        int id PK
        m2o product_id FK
        m2o location_id FK
        m2o package_id FK
        float quantity
        float reserved_quantity
    }
    product_template {
        int id PK
        char name
        bool is_storable
        float weight
        float wh3d_length "NEW box length (m)"
        float wh3d_width "NEW box width (m)"
        float wh3d_height "NEW box height (m)"
        selection wh3d_abc_class "NEW A / B / C"
    }
    product_product {
        int id PK
        m2o product_tmpl_id FK
        char default_code
    }
    stock_storage_category {
        int id PK
        char name
        selection allow_new_product "empty / same / mixed"
        float max_weight
    }
    stock_storage_category_capacity {
        int id PK
        m2o storage_category_id FK
        m2o package_type_id FK
        m2o product_id FK
        float quantity
    }
    stock_putaway_rule {
        int id PK
        m2o location_in_id FK "when product arrives in"
        m2o location_out_id FK "store to"
        selection sublocation "closest_location ..."
        m2o storage_category_id FK
        m2o category_id FK
    }
    stock_picking {
        int id PK
        char name "TW/IN/00005"
        m2o picking_type_id FK
        m2o location_id FK
        m2o location_dest_id FK
        selection state
    }
    stock_picking_type {
        int id PK
        selection code "incoming / outgoing / internal"
        m2o warehouse_id FK
        bool set_package_type
    }
    stock_move {
        int id PK
        m2o picking_id FK
        m2o product_id FK
        float product_uom_qty
    }
    stock_move_line {
        int id PK
        m2o move_id FK
        m2o location_id FK "from"
        m2o location_dest_id FK "to (set by putaway)"
        m2o result_package_id FK
        float quantity
    }
    stock_package {
        int id PK
        char name "PACK0000001"
        m2o package_type_id FK
    }
    stock_package_type {
        int id PK
        char name "Pallet (EUR-size)"
    }

    %% ---------- New in warehouse_3d ----------
    warehouse_rack_row {
        int id PK
        char code "P05 (letter + 2 digits)"
        selection kind "pallet / shelf"
        m2o warehouse_id FK
        m2o location_id FK "zone, e.g. WH/Stock/PR"
        m2o storage_category_id FK "copied to every slot"
        float x "corner on the floor plan (m)"
        float y
        int bays
        float bay_width
        float depth
        int levels
        float level_height
        int slots_per_level "max 26 (A-Z)"
        bool active
    }
    warehouse_layout_area {
        int id PK
        char name
        selection kind "area / dock"
        m2o warehouse_id FK
        float x
        float y
        float width "along X"
        float depth "along Y"
        char color "#rrggbb"
    }

    %% ---------- Standard relations ----------
    stock_warehouse ||--o{ stock_location : "owns"
    stock_location ||--o{ stock_location : "parent of"
    stock_location ||--o{ stock_quant : "holds"
    product_template ||--|{ product_product : "variants"
    product_product ||--o{ stock_quant : "stocked as"
    stock_storage_category ||--o{ stock_location : "applies to"
    stock_storage_category ||--o{ stock_storage_category_capacity : "limits"
    stock_package_type ||--o{ stock_storage_category_capacity : "counted by"
    stock_storage_category ||--o{ stock_putaway_rule : "filters"
    stock_location ||--o{ stock_putaway_rule : "in / out"
    stock_picking_type ||--o{ stock_picking : "type of"
    stock_warehouse ||--o{ stock_picking_type : "has"
    stock_picking ||--o{ stock_move : "contains"
    stock_move ||--o{ stock_move_line : "detailed by"
    stock_move_line }o--|| stock_location : "to / from"
    stock_package ||--o{ stock_move_line : "packs"
    stock_package_type ||--o{ stock_package : "type of"

    %% ---------- Our relations ----------
    stock_warehouse ||--o{ warehouse_rack_row : "NEW has rows"
    stock_warehouse ||--o{ warehouse_layout_area : "NEW has areas + docks"
    warehouse_rack_row }o--|| stock_location : "NEW zone parent"
    warehouse_rack_row ||--o{ stock_location : "NEW generates row/bay/level/slot"
    stock_storage_category ||--o{ warehouse_rack_row : "NEW set on row"
```

**Reading it:** Odoo already models a warehouse as a tree of `stock.location` records holding
`stock.quant`s. We did not replace any of that. A `warehouse.rack.row` is a *generator*: from its
shape (bays × levels × slots) it creates the location tree under its zone and tags each node with
`wh3d_*` fields so the 3D view knows where it sits. `warehouse.layout.area` is drawing-only (no stock).

---

## 2. Class diagram: extended vs new models

```mermaid
classDiagram
    direction LR

    class stock_warehouse["stock.warehouse"] {
        <<_inherit>>
        +wh3d_length / width / height
        +wh3d_area_ids
        +wh3d_get_scene()
        +wh3d_get_slots(location_ids)
        +wh3d_get_layout()
        +wh3d_list_warehouses()
        +wh3d_default_warehouse_id()
        -_check_wh3d_contains()
        -_check_wh3d_areas_clear_of_rows()
    }
    class stock_location["stock.location"] {
        <<_inherit>>
        +wh3d_rack_row_id
        +wh3d_node
        +wh3d_bay / level / position
        +write() locks name/parent/type of generated nodes
    }
    class stock_quant["stock.quant"] {
        <<_inherit>>
        +create() / write() / unlink()
        -_wh3d_notify(locations)
        -_wh3d_send_changed() one bus message per commit
    }
    class product_template["product.template"] {
        <<_inherit>>
        +wh3d_length / width / height
        +wh3d_abc_class
    }
    class warehouse_rack_row["warehouse.rack.row"] {
        <<new model>>
        +code, kind, x, y
        +bays, bay_width, depth
        +levels, level_height, slots_per_level
        +create() / write() / unlink() sync locations
        +wh3d_save_layout(warehouse_id, changes) all or nothing
        +action_generate_locations()
        -_sync_locations()
        -_check_removal() refuses removing stocked slots
        -_check_layout() inside building, no overlap
    }
    class warehouse_layout_area["warehouse.layout.area"] {
        <<new model>>
        +name, kind (area / dock)
        +x, y, width, depth, color
        -_check_* inside building, dock on a wall, clear of rows
    }

    stock_warehouse "1" --> "*" warehouse_rack_row : rows
    stock_warehouse "1" --> "*" warehouse_layout_area : areas
    warehouse_rack_row "1" --> "*" stock_location : generates
    stock_location "1" --> "*" stock_quant : holds
    stock_quant ..> stock_location : notifies 3D view
```

`<<_inherit>>` = an existing Odoo model we add fields/methods to. `<<new model>>` = a table this
module creates.

---

## 3. Flow: editor → Inventory → 3D view

```mermaid
flowchart LR
    subgraph Client["Browser (OWL client actions)"]
        ED["Layout Editor<br/>2D plan"]
        V3["3D View<br/>Three.js"]
        Q["UpdateQueue<br/>live.js"]
    end

    subgraph Ours["warehouse_3d (Python)"]
        SAVE["wh3d_save_layout()"]
        ROW["warehouse.rack.row"]
        AREA["warehouse.layout.area"]
        SYNC["_sync_locations()"]
        SCENE["wh3d_get_scene()<br/>wh3d_get_slots()"]
        NOTIFY["stock.quant hooks<br/>_wh3d_notify()"]
    end

    subgraph Odoo["Odoo Inventory (standard)"]
        LOC["stock.location tree<br/>row / bay / level / slot"]
        PUT["Putaway rules +<br/>storage categories"]
        PICK["Receipts / Deliveries<br/>stock.picking"]
        QUANT["stock.quant"]
        BUS["bus.bus<br/>'warehouse_3d/stock'"]
    end

    ED -- "Save (rows + areas + docks)" --> SAVE
    SAVE --> ROW
    SAVE --> AREA
    ROW --> SYNC
    SYNC -- "create / rename / archive" --> LOC

    PICK -- "move lines" --> PUT
    PUT -- "chooses a slot" --> LOC
    PICK -- "validate" --> QUANT
    QUANT --> NOTIFY
    NOTIFY -- "one message per commit" --> BUS
    BUS -- "location_ids" --> Q
    Q -- "refetch changed slots" --> SCENE
    V3 -- "open" --> SCENE
    SCENE -- "building, areas, rows, slots + stock" --> V3
    LOC -.-> SCENE
    QUANT -.-> SCENE
```

**In one sentence:** we keep Odoo's own locations, quants, putaway and transfers untouched. We add
a layout layer (rack rows, areas, building size) that *generates* those locations, and a
read/notify layer (scene RPC + bus message) that draws them in 3D and updates them live.
