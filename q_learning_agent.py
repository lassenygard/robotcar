# q_learning_agent.py

import numpy as np
import random

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
        if next_state not in self.q_table:
            self.q_table[next_state] = [0] * len(self.actions)

        target = reward + self.discount_factor * np.max(self.q_table[next_state])
        self.q_table[state][action] += self.learning_rate * (target - self.q_table[state][action])