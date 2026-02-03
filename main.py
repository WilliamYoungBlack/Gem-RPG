import pygame
import sys
import random
from dataclasses import dataclass

# --- CONFIGURATION ---
WINDOW_WIDTH = 640
WINDOW_HEIGHT = 480
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 240
FPS = 60

# Colors
COLOR_BG = (15, 15, 20)
COLOR_WALL = (85, 98, 112)
COLOR_PLAYER = (255, 107, 107)
COLOR_MONSTER = (78, 205, 196)
COLOR_ITEM = (255, 215, 0)      # Gold
COLOR_ATTACK = (255, 255, 255)

# --- ECS CORE ---
class ECSManager:
    """
    A lightweight Entity Component System manager.
    Entities are just Integer IDs.
    Components are stored in dictionaries keyed by Component Type.
    """
    def __init__(self):
        self.next_entity_id = 0
        self.components = {} # {ComponentType: {entity_id: component_data}}
        self.entities_to_destroy = []

    def create_entity(self):
        entity = self.next_entity_id
        self.next_entity_id += 1
        return entity

    def add_component(self, entity, component):
        comp_type = type(component)
        if comp_type not in self.components:
            self.components[comp_type] = {}
        self.components[comp_type][entity] = component

    def get_component(self, entity, comp_type):
        return self.components.get(comp_type, {}).get(entity)

    def get_entities_with(self, *comp_types):
        """
        Returns a list of entity IDs that possess ALL specified component types.
        """
        if not comp_types:
            return []
        
        # Get the set of entities for the first component type
        entities = set(self.components.get(comp_types[0], {}).keys())
        
        # Intersect with sets of other component types
        for ct in comp_types[1:]:
            entities &= set(self.components.get(ct, {}).keys())
        
        return list(entities)

    def destroy_entity(self, entity):
        self.entities_to_destroy.append(entity)

    def process_destruction(self):
        if not self.entities_to_destroy:
            return
        for entity in self.entities_to_destroy:
            for comp_type in self.components:
                if entity in self.components[comp_type]:
                    del self.components[comp_type][entity]
        self.entities_to_destroy.clear()

# --- COMPONENT DEFINITIONS (Data Only) ---
@dataclass
class Transform:
    x: float
    y: float
    width: int = 16
    height: int = 16

@dataclass
class Velocity:
    x: float = 0
    y: float = 0
    speed: float = 0

@dataclass
class Sprite:
    color: tuple
    visible: bool = True

@dataclass
class Collider:
    is_solid: bool = True      # Blocks movement (Walls)
    is_trigger: bool = False   # Passes through but triggers events (Items)
    tag: str = "default"       # "wall", "monster", "player"

@dataclass
class InputControl:
    """Tag component for the entity controlled by the player"""
    pass

@dataclass
class AIBehavior:
    """Simple AI State"""
    behavior_type: str = "wander"
    timer: float = 0

@dataclass
class CombatStats:
    hp: int = 10
    max_hp: int = 10
    damage: int = 1

@dataclass
class ItemData:
    name: str
    value: int

# --- SYSTEMS (Logic Only) ---

class InputSystem:
    def __init__(self, ecs, input_mgr):
        self.ecs = ecs
        self.input_mgr = input_mgr

    def update(self):
        # Find the entity with InputControl
        entities = self.ecs.get_entities_with(InputControl, Velocity)
        for entity in entities:
            vel = self.ecs.get_component(entity, Velocity)
            
            # Get normalized vector from InputManager
            move_vec = self.input_mgr.get_movement_vector()
            vel.x = move_vec.x
            vel.y = move_vec.y
            
            # Attack Handling (Basic)
            if self.input_mgr.is_attack_pressed():
                print(f"Entity {entity} Attacked!") 
                # (Attack logic would spawn a temporary 'Hitbox' entity here)

class PhysicsSystem:
    def __init__(self, ecs):
        self.ecs = ecs

    def update(self, dt):
        movables = self.ecs.get_entities_with(Transform, Velocity)
        obstacles = self.ecs.get_entities_with(Transform, Collider)

        for entity in movables:
            vel = self.ecs.get_component(entity, Velocity)
            pos = self.ecs.get_component(entity, Transform)

            if vel.x == 0 and vel.y == 0:
                continue

            # Move X
            pos.x += vel.x * vel.speed * dt
            player_rect_x = pygame.Rect(round(pos.x), round(pos.y), pos.width, pos.height)
            
            # X Collision
            for wall in obstacles:
                if wall == entity: continue # Don't collide with self
                
                wall_pos = self.ecs.get_component(wall, Transform)
                wall_col = self.ecs.get_component(wall, Collider)
                
                if not wall_col.is_solid: continue # Skip triggers like Items for now

                wall_rect = pygame.Rect(wall_pos.x, wall_pos.y, wall_pos.width, wall_pos.height)
                
                if player_rect_x.colliderect(wall_rect):
                    if vel.x > 0: pos.x = wall_rect.left - pos.width
                    elif vel.x < 0: pos.x = wall_rect.right
            
            # Move Y
            pos.y += vel.y * vel.speed * dt
            player_rect_y = pygame.Rect(round(pos.x), round(pos.y), pos.width, pos.height)

            # Y Collision
            for wall in obstacles:
                if wall == entity: continue
                
                wall_pos = self.ecs.get_component(wall, Transform)
                wall_col = self.ecs.get_component(wall, Collider)
                
                if not wall_col.is_solid: continue

                wall_rect = pygame.Rect(wall_pos.x, wall_pos.y, wall_pos.width, wall_pos.height)
                
                if player_rect_y.colliderect(wall_rect):
                    if vel.y > 0: pos.y = wall_rect.top - pos.height
                    elif vel.y < 0: pos.y = wall_rect.bottom

class AISystem:
    def __init__(self, ecs):
        self.ecs = ecs

    def update(self, dt):
        monsters = self.ecs.get_entities_with(Transform, Velocity, AIBehavior)
        for entity in monsters:
            ai = self.ecs.get_component(entity, AIBehavior)
            vel = self.ecs.get_component(entity, Velocity)
            
            ai.timer -= dt
            if ai.timer <= 0:
                # Pick random direction
                ai.timer = random.uniform(1.0, 3.0)
                vel.x = random.choice([-1, 0, 1])
                vel.y = random.choice([-1, 0, 1])
                
                # Normalize if moving diagonal
                if vel.x != 0 or vel.y != 0:
                    vec = pygame.math.Vector2(vel.x, vel.y).normalize()
                    vel.x, vel.y = vec.x, vec.y

class RenderSystem:
    def __init__(self, ecs, surface):
        self.ecs = ecs
        self.surface = surface

    def update(self, camera_offset):
        # We need to sort by Y position for depth (2.5D look)
        renderables = self.ecs.get_entities_with(Transform, Sprite)
        
        # Sort entities by their Y position (plus height)
        renderables.sort(key=lambda e: self.ecs.get_component(e, Transform).y)

        for entity in renderables:
            trans = self.ecs.get_component(entity, Transform)
            sprite = self.ecs.get_component(entity, Sprite)
            
            if not sprite.visible: continue

            # Create Rect for drawing
            draw_x = round(trans.x - camera_offset.x)
            draw_y = round(trans.y - camera_offset.y)
            
            # Simple colored block for now (In real game, blit an image)
            pygame.draw.rect(self.surface, sprite.color, (draw_x, draw_y, trans.width, trans.height))

# --- FACTORIES (The "Classes" you asked for) ---

def create_player(ecs, x, y):
    e = ecs.create_entity()
    ecs.add_component(e, Transform(x, y, 16, 16))
    ecs.add_component(e, Velocity(speed=80))
    ecs.add_component(e, Sprite(COLOR_PLAYER))
    ecs.add_component(e, Collider(tag="player"))
    ecs.add_component(e, InputControl()) # Marks this as the player
    ecs.add_component(e, CombatStats(hp=20, damage=2))
    return e

def create_monster(ecs, x, y):
    e = ecs.create_entity()
    ecs.add_component(e, Transform(x, y, 16, 16))
    ecs.add_component(e, Velocity(speed=40)) # Slower than player
    ecs.add_component(e, Sprite(COLOR_MONSTER))
    ecs.add_component(e, Collider(tag="monster"))
    ecs.add_component(e, AIBehavior())
    ecs.add_component(e, CombatStats(hp=5, damage=1))
    return e

def create_item(ecs, x, y, name="Potion"):
    e = ecs.create_entity()
    ecs.add_component(e, Transform(x, y, 12, 12))
    ecs.add_component(e, Sprite(COLOR_ITEM))
    # Trigger = True means you can walk over it
    ecs.add_component(e, Collider(is_solid=False, is_trigger=True, tag="item"))
    ecs.add_component(e, ItemData(name=name, value=10))
    return e

def create_wall(ecs, x, y, w, h):
    e = ecs.create_entity()
    ecs.add_component(e, Transform(x, y, w, h))
    ecs.add_component(e, Sprite(COLOR_WALL))
    ecs.add_component(e, Collider(is_solid=True, tag="wall"))
    return e

# --- INPUT MANAGER (Reused from previous code) ---
class InputManager:
    def __init__(self):
        pygame.joystick.init()
        self.joysticks = {}
        self._init_controllers()

    def _init_controllers(self):
        for i in range(pygame.joystick.get_count()):
            self._add_joy(i)

    def _add_joy(self, device_index):
        joy = pygame.joystick.Joystick(device_index)
        joy.init()
        self.joysticks[joy.get_instance_id()] = joy

    def handle_hotplug(self, event):
        if event.type == pygame.JOYDEVICEADDED:
            self._add_joy(event.device_index)
        elif event.type == pygame.JOYDEVICEREMOVED:
            if event.instance_id in self.joysticks:
                del self.joysticks[event.instance_id]

    def get_movement_vector(self):
        move = pygame.math.Vector2(0, 0)
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]: move.x = -1
        if keys[pygame.K_RIGHT]: move.x = 1
        if keys[pygame.K_UP]: move.y = -1
        if keys[pygame.K_DOWN]: move.y = 1
        
        if self.joysticks:
            joy = list(self.joysticks.values())[0]
            if abs(joy.get_axis(0)) > 0.2: move.x = joy.get_axis(0)
            if abs(joy.get_axis(1)) > 0.2: move.y = joy.get_axis(1)

        if move.length() > 0: move = move.normalize()
        return move

    def is_attack_pressed(self):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_z] or keys[pygame.K_SPACE]: return True
        if self.joysticks:
            joy = list(self.joysticks.values())[0]
            if joy.get_button(0) or joy.get_button(2): return True # A or X
        return False

# --- MAIN ENGINE ---
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.display_surface = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
        pygame.display.set_caption("ECS ARPG")
        self.clock = pygame.time.Clock()
        self.running = True

        # Initialize ECS
        self.ecs = ECSManager()
        self.input_mgr = InputManager()
        
        # Initialize Systems
        self.input_system = InputSystem(self.ecs, self.input_mgr)
        self.physics_system = PhysicsSystem(self.ecs)
        self.ai_system = AISystem(self.ecs)
        self.render_system = RenderSystem(self.ecs, self.display_surface)

        # Initialize World
        self._init_level()

    def _init_level(self):
        # 1. Create Walls
        for _ in range(20):
            create_wall(self.ecs, random.randint(0, 300), random.randint(0, 200), 32, 32)
        
        # 2. Create Monsters
        for _ in range(5):
            create_monster(self.ecs, random.randint(50, 250), random.randint(50, 200))

        # 3. Create Items
        create_item(self.ecs, 200, 200, "Gold Coin")

        # 4. Create Player (Store ID for camera)
        self.player_id = create_player(self.ecs, 100, 100)

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0

            # 1. Event Handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                self.input_mgr.handle_hotplug(event)

            # 2. Run Systems
            self.input_system.update()
            self.ai_system.update(dt)
            self.physics_system.update(dt)
            
            # 3. Cleanup
            self.ecs.process_destruction()

            # 4. Camera Logic (Simple centering)
            # Fetch player transform directly to update camera
            player_pos = self.ecs.get_component(self.player_id, Transform)
            camera_offset = pygame.math.Vector2(0, 0)
            if player_pos:
                camera_offset.x = player_pos.x - INTERNAL_WIDTH // 2
                camera_offset.y = player_pos.y - INTERNAL_HEIGHT // 2

            # 5. Render
            self.display_surface.fill(COLOR_BG)
            self.render_system.update(camera_offset)
            
            # Scale to Window
            pygame.transform.scale(self.display_surface, (self.screen.get_width(), self.screen.get_height()), self.screen)
            pygame.display.flip()

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    Game().run()
