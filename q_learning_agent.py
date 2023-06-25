# q_learning_agent.py

import numpy as np
import random
import pickle
import os

class QlearningAgent:
    def __init__(self, actions, learning_rate=0.1, discount_factor=0.9, exploration_rate=0.3):
        self.actions = actions
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.exploration_rate = exploration_rate
        self.q_table = {}

    def get_action(self, state):
        if random.uniform(0, 1) < self.exploration_rate:
            return random.choice(self.actions)
        else:
            return self.get_best_action(state)

    def get_best_action(self, state):
        if state not in self.q_table:
            self.q_table[state] = [0] * len(self.actions)
        return np.argmax(self.q_table[state])

    def update(self, state, action, reward, next_state):
        if state not in self.q_table:
            self.q_table[state] = [0] * len(self.actions)
        flat_next_state = [item for sublist in next_state for item in sublist]
        if tuple(flat_next_state) not in self.q_table:

            self.q_table[next_state] = [0] * len(self.actions)

        flat_next_state = [item for sublist in next_state for item in sublist]
        target = reward + self.discount_factor * np.max(self.q_table[tuple(flat_next_state)])
        self.q_table[state][action] += self.learning_rate * (target - self.q_table[state][action])
    
    def save_q_table(self, filepath="qtable/q_table.pkl"):
        with open(filepath, 'wb') as f:
            pickle.dump(self.q_table, f)

    def load_q_table(self, filepath="qtable/q_table.pkl"):
        if os.path.isfile(filepath):
            with open(filepath, 'rb') as f:
                self.q_table = pickle.load(f)
